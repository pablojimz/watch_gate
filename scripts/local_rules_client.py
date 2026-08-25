#!/usr/bin/env python3
"""Auto-verificación de reglas Semgrep/YARA para ejecuciones LOCALES
(fuera de CI) del análisis estático de `watch_gate`.

## Problema que resuelve

`.github/workflows/sync-rules.yml` / `reconcile-rules.yml` mantienen
`rules/` de este repo al día en el runner de CI cada vez que
`pablojimz/Repo-reglas-SEMGREP-y-YARA` publica una versión nueva (ver
`docs/integracion_repo_reglas.md`). Pero esa actualización vive en el
repo REMOTO de `watch_gate`: el checkout local de un desarrollador no se
entera hasta que hace `git pull`. Entretanto, ejecutar el analizador en
local usaría reglas potencialmente desactualizadas sin ningún aviso.

Este módulo desacopla "tener `watch_gate` actualizado localmente" de "el
análisis usa las reglas correctas": en vez de leer `rules/` del propio
checkout, pregunta directamente al repo de reglas cuál es la última
versión publicada y descarga/verifica bajo demanda, en el momento, solo
lo que hace falta -- cacheando lo ya verificado para no repetir trabajo
en ejecuciones sucesivas contra la misma versión.

No sustituye al mecanismo de CI (`scripts/sync_rules.py`): ese script
ACTIVA reglas verificadas dentro del árbol git de `watch_gate` (las
comitea); este módulo NUNCA escribe dentro del repo -- vive
enteramente en una caché local fuera del árbol git (por defecto
`~/.cache/watch_gate/`, ver variables de entorno más abajo) y expone
únicamente rutas de lectura a quien lo llame.

## Cómo funciona (resumen; ver docstrings de cada función para el detalle)

1. `get_verified_rules()` pide SIEMPRE `manifest.json` (asset de la
   última Release publicada, o de un tag exacto vía `ref=`) a la
   Releases API de GitHub -- una petición HTTP barata, nada de clonar --
   así la "versión activa" que ve este módulo nunca puede quedarse
   desincronizada por falta de un `git pull` local.
2. Para cada clave pedida (lenguaje custom / `vendor/carpeta`
   third-party / categoría YARA), compara el hash que el manifest
   publica para esa clave contra lo último que este módulo verificó con
   éxito (cacheado en disco, ver `verified_state_file()`). Si coincide,
   NO vuelve a tocar red ni Git ni a recalcular el hash: confía en la
   verificación anterior y devuelve la ruta local ya conocida.
3. Solo para las claves que de verdad hacen falta (primera vez, hash
   cambiado, o directorio local ausente), amplía el sparse-checkout de
   un clon disperso persistente y reutilizable (`repo_cache_dir()`,
   `git clone --filter=blob:none --sparse --no-checkout`), hace
   checkout del TAG exacto de la versión activa y `git lfs pull`
   acotado a esas rutas.
4. Recalcula el hash SOLO de esas claves (mismo método determinista que
   `scripts/rules_hash.py` / `build_release_manifest.py` del repo de
   reglas) y lo compara con el manifest, clave a clave.
5. Fallo cerrado, todo-o-nada: si UNA sola clave pedida en esta llamada
   no verifica, se lanza `RulesVerificationError` con la lista exacta de
   claves fallidas, NO se actualiza el estado cacheado y NO se devuelve
   ninguna ruta -- ni siquiera las de las claves que sí verificaron.

## Uso como librería (desde el analizador)

    import sys
    sys.path.insert(0, "<ruta a>/watch_gate/scripts")  # scripts/ no es un paquete instalado
    from local_rules_client import get_verified_rules, RulesVerificationError

    try:
        rules = get_verified_rules(
            languages=["python", "javascript"],
            third_party=["trailofbits/rs"],
            include_yara=True,  # SIEMPRE trae TODAS las categorías publicadas
        )
    except RulesVerificationError as exc:
        # exc.failed_keys -- lista de claves que no verificaron
        raise

    rules.version               # "v0.0.3"
    rules.custom["python"]      # Path local verificado, listo para pasar a Semgrep
    rules.third_party["trailofbits/rs"]
    rules.yara["webshells"]

## Uso como CLI

    export RULES_REPO_TOKEN=ghp_...
    python scripts/local_rules_client.py \\
        --language python --language javascript \\
        --third-party trailofbits/rs \\
        --all-yara

Imprime la versión activa verificada y la ruta local de cada clave
descargada; termina con código de salida distinto de 0 (y sin imprimir
ninguna ruta parcial) si alguna clave no verifica.

`--all-languages` / `--all-third-party` verifican TODO el catálogo
publicado de esa familia (ignoran `--language` / `--third-party`) --
pensado para un consumidor que necesita el catálogo completo sin conocer
de antemano qué lenguajes tienen carpeta `custom/` propia en el repo de
reglas (ver `watchgate/core/layers/static_layer.py`, que usa
`get_verified_rules(include_all_custom=True, include_all_third_party=True,
include_yara=True)` como primer paso de su resolución de reglas).

## Variables de entorno

- `RULES_REPO_TOKEN` (obligatoria): token con acceso de lectura a
  `pablojimz/Repo-reglas-SEMGREP-y-YARA` (mismo secret que usa CI, ver
  §5.2 de `docs/integracion_repo_reglas.md`: tiene que ser un classic
  PAT con scope `repo`, un fine-grained PAT no da acceso a la API de Git
  LFS).
- `WATCHGATE_RULES_REPO_CACHE_DIR` (opcional): dónde vive el clon
  disperso persistente. Por defecto `~/.cache/watch_gate/rules-repo`.
- `WATCHGATE_RULES_VERIFIED_STATE_FILE` (opcional): dónde vive el
  registro de qué claves se verificaron con qué hash. Por defecto
  `~/.cache/watch_gate/verified_state.json`.

## Límite de confianza asumido conscientemente

El estado cacheado (`verified_state_file()`) y el clon disperso
(`repo_cache_dir()`) son ficheros locales bajo control exclusivo de
quien ejecuta este script. Una clave con hash cacheado igual al del
manifest actual se acepta SIN releer ni rehashear su carpeta local: si
alguien con acceso al propio filesystem del desarrollador editase a
mano el contenido ya verificado en la caché, este mecanismo no lo
detectaría en la siguiente ejecución. Es un límite de confianza
deliberado (igual que confiar en la propia caché de `pip`/`npm`
locales): quien puede escribir en tu `$HOME` ya tiene opciones mucho
más directas que esa. La propiedad que este módulo SÍ garantiza es que
ningún contenido descargado de red se activa sin pasar, al menos una
vez, por la verificación de hash contra el manifest firmado por la
Release.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# scripts/ no es un paquete Python instalado (son scripts sueltos, ver
# convención ya existente en rules_hash.py / sync_rules.py) -- se añade su
# propio directorio a sys.path para poder hacer `import sync_rules` /
# `import rules_hash` tanto ejecutando este fichero directamente como
# importándolo como módulo desde otra ruta.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from rules_hash import compute_dir_hash, hashes_match  # noqa: E402
from sync_rules import (  # noqa: E402
    _assert_no_lfs_pointers,
    _flatten_third_party,
    _parse_third_party_entries,
    _run_git,
    _validate_key_segment,
    fetch_release_manifest,
)

# ---------------------------------------------------------------------------
# Repo de reglas y token: fijados explícitamente (spec del usuario pide NO
# asumir owner/repo/secret distintos de los indicados). Si algún día hiciera
# falta apuntar a otro repo de reglas, se cambia aquí, no vía flag de CLI --
# a diferencia de sync_rules.py (--rules-repo), este script no está pensado
# para reutilizarse contra un repo de reglas distinto.
# ---------------------------------------------------------------------------
RULES_REPO = "pablojimz/Repo-reglas-SEMGREP-y-YARA"
DEFAULT_MANIFEST_ASSET = "manifest.json"
ENV_TOKEN = "RULES_REPO_TOKEN"

# Rutas dentro del repo de reglas -- mismas constantes/convención que
# scripts/sync_rules.py (ver ese módulo para la justificación de cada una).
CUSTOM_PREFIX = "rules/semgrep/custom"
THIRD_PARTY_PREFIX = "rules/semgrep/third-party"
YARA_PREFIX = "dist/yara_scored"

# Variables de entorno para las dos ubicaciones de caché persistente. Nunca
# se hardcodea una ruta absoluta: siempre configurable, con un valor por
# defecto bajo el HOME del usuario (spec del usuario, requisito explícito).
ENV_REPO_CACHE_DIR = "WATCHGATE_RULES_REPO_CACHE_DIR"
ENV_STATE_FILE = "WATCHGATE_RULES_VERIFIED_STATE_FILE"


def _default_cache_root() -> Path:
    return Path.home() / ".cache" / "watch_gate"


def repo_cache_dir() -> Path:
    """Directorio del clon disperso persistente y reutilizable del repo de
    reglas. Configurable por `WATCHGATE_RULES_REPO_CACHE_DIR`; por defecto
    `~/.cache/watch_gate/rules-repo`."""
    override = os.environ.get(ENV_REPO_CACHE_DIR)
    return Path(override).expanduser() if override else _default_cache_root() / "rules-repo"


def verified_state_file() -> Path:
    """Fichero JSON con qué claves se verificaron con qué hash. Configurable
    por `WATCHGATE_RULES_VERIFIED_STATE_FILE`; por defecto
    `~/.cache/watch_gate/verified_state.json`."""
    override = os.environ.get(ENV_STATE_FILE)
    if override:
        return Path(override).expanduser()
    return _default_cache_root() / "verified_state.json"


class RulesClientError(RuntimeError):
    """Error base de este módulo: configuración inválida, red, o
    inconsistencia del repo de reglas -- cualquier fallo que NO sea "una
    clave no verificó por hash" (para eso, ver `RulesVerificationError`)."""


class RulesVerificationError(RulesClientError):
    """Fallo cerrado: al menos una clave pedida no verificó contra el
    manifest. `failed_keys` lleva la lista exacta (nunca un booleano
    global) -- requisito explícito: poder distinguir qué clave concreta
    falló. Levantar esta excepción implica que NO se ha actualizado el
    estado cacheado y que el llamador NO recibe ninguna ruta, ni siquiera
    de las claves que sí verificaron en la misma llamada."""

    def __init__(self, failed_keys: list[str], version: str | None):
        self.failed_keys = failed_keys
        self.version = version
        super().__init__(
            f"Verificación de integridad fallida para {len(failed_keys)} clave(s) "
            f"de la versión {version!r}: {', '.join(failed_keys)}. Fallo cerrado: "
            "no se activa ninguna clave (ni las que sí verificaron) y no se ha "
            "actualizado el estado cacheado."
        )


@dataclass
class VerifiedRules:
    """Resultado de `get_verified_rules()`: rutas locales YA verificadas
    por hash, organizadas exactamente como pide el requisito (6) -- por
    lenguaje custom, por `<vendor>/<carpeta>` third-party y por categoría
    YARA.

    `manifest` es el manifest.json COMPLETO tal cual lo publicó la Release
    (no solo los hashes) -- se conserva para que el consumidor pueda leer
    campos declarativos que no forman parte de la verificación por hash,
    como `official_registry_configs` (IDs del registro oficial de Semgrep
    que el propio consumidor debe pedir en caliente; nunca contenido de
    regla, así que no hay nada que verificar por hash aquí -- ver
    `.claude/analisisLicenciaSemgrepOficial.md` en el repo de reglas)."""

    version: str
    custom: dict[str, Path] = field(default_factory=dict)
    third_party: dict[str, Path] = field(default_factory=dict)
    yara: dict[str, Path] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Etiquetas de clave -- mismo formato "semgrep.custom.<lenguaje>" /
# "semgrep.third_party.<vendor>.<carpeta>" / "yara.<categoria>" que usa
# scripts/sync_rules.py, para que los mensajes de error/estado sean
# reconocibles entre ambos mecanismos (CI y local).
# ---------------------------------------------------------------------------


def _key_label_custom(lang: str) -> str:
    return f"semgrep.custom.{lang}"


def _key_label_third_party(vendor: str, carpeta: str) -> str:
    return f"semgrep.third_party.{vendor}.{carpeta}"


def _key_label_yara(category: str) -> str:
    return f"yara.{category}"


def _expected_hashes_by_key(manifest: dict[str, Any]) -> dict[str, str]:
    """Aplana el árbol de hashes del manifest a un dict plano por
    "key_label", para poder mirar el hash esperado de una clave concreta
    en O(1) sin repetir la navegación anidada en cada sitio."""
    hashes = manifest.get("hashes", {})
    semgrep = hashes.get("semgrep", {})
    custom = semgrep.get("custom", {})
    third_party = semgrep.get("third_party", {})
    yara = hashes.get("yara", {})

    out: dict[str, str] = {}
    for lang, digest in custom.items():
        out[_key_label_custom(lang)] = digest
    for vendor, carpetas in third_party.items():
        for carpeta, digest in carpetas.items():
            out[_key_label_third_party(vendor, carpeta)] = digest
    for category, digest in yara.items():
        out[_key_label_yara(category)] = digest
    return out


def _resolve_requests(
    manifest: dict[str, Any],
    languages: list[str],
    third_party: list[str],
    include_yara: bool,
    include_all_custom: bool = False,
    include_all_third_party: bool = False,
) -> tuple[list[str], list[tuple[str, str]], list[str]]:
    """Normaliza y valida lo pedido por el llamador.

    - `languages` / `third_party` ("vendor/carpeta"): tal cual lo pide el
      llamador (deduplicado y ordenado) -- salvo que `include_all_custom`/
      `include_all_third_party` estén activos, en cuyo caso se ignoran y
      se piden TODOS los lenguajes/carpetas third-party que el manifest
      publique. Existe para un llamador (p. ej. `static_layer.py`) que
      necesita el catálogo completo sin conocer de antemano qué lenguajes
      concretos tienen carpeta `custom/` propia en el repo de reglas --
      pedir explícitamente un lenguaje sin esa carpeta haría fallar la
      verificación por una clave que legítimamente no existe (ver
      requisito (5): sin hash publicado, la clave se trata como fallo).
    - YARA: si `include_yara`, SIEMPRE TODAS las categorías que el
      manifest publica -- nunca una selección parcial (requisito
      explícito (6): "así es como se decidió que funcione el análisis
      YARA"), nunca las que pida el llamador a la carta. Mismo criterio
      que `include_all_custom`/`include_all_third_party`, aplicado desde
      el principio solo a YARA.

    Cada segmento se valida contra un charset seguro (reutilizando
    `sync_rules._validate_key_segment`) antes de poder llegar a construir
    ninguna ruta de disco con él -- mismo motivo que en sync_rules.py: un
    "lenguaje" o "categoría YARA" con `../` no debe poder escapar de la
    caché local, ni viniendo de un argumento de CLI ni de una clave del
    manifest descargado.
    """
    semgrep_hashes = manifest.get("hashes", {}).get("semgrep", {})
    yara_hashes = manifest.get("hashes", {}).get("yara", {})

    if include_all_custom:
        langs = sorted(
            _validate_key_segment(lang, "Idioma") for lang in semgrep_hashes.get("custom", {})
        )
    else:
        langs = sorted({_validate_key_segment(lang, "Idioma") for lang in languages})

    if include_all_third_party:
        tp_pairs = sorted(
            (
                _validate_key_segment(vendor, "Vendor third-party"),
                _validate_key_segment(carpeta, "Carpeta third-party"),
            )
            for vendor, carpeta in _flatten_third_party(semgrep_hashes.get("third_party", {}))
        )
    else:
        tp_pairs = sorted(
            {
                (
                    _validate_key_segment(vendor, "Vendor third-party"),
                    _validate_key_segment(carpeta, "Carpeta third-party"),
                )
                for vendor, carpeta in _parse_third_party_entries(third_party)
            }
        )

    yara_categories = (
        sorted(_validate_key_segment(category, "Categoría YARA") for category in yara_hashes)
        if include_yara
        else []
    )
    return langs, tp_pairs, yara_categories


# ---------------------------------------------------------------------------
# Clon disperso persistente (distinto del checkout "de usar y tirar" en un
# tempdir que hace scripts/sync_rules.py: aquí el objetivo es justo lo
# contrario, reutilizar el MISMO clon entre ejecuciones sucesivas).
# ---------------------------------------------------------------------------


def _authenticated_url(token: str) -> str:
    return f"https://x-access-token:{token}@github.com/{RULES_REPO}.git"


def _git_output(args: list[str], cwd: Path) -> str:
    """Como `sync_rules._run_git`, pero devolviendo stdout -- hace falta
    para leer `git sparse-checkout list` (qué carpetas ya están ampliadas
    de una ejecución anterior de este mismo módulo)."""
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"Fallo `git {' '.join(args)}`: {result.stderr.strip()}")
    return result.stdout


def _ensure_repo_cache(cache_dir: Path, token: str) -> None:
    """Envoltorio fino que calcula la URL autenticada real de
    `RULES_REPO` y delega en `_ensure_repo_cache_from_url`. Separado en
    dos funciones -- mismo patrón que
    `sync_rules._checkout_rule_folders`/`_checkout_from_url` -- para
    poder testear la mecánica real de git+LFS contra un repo local
    (`file://`) sin necesitar un token real ni red."""
    _ensure_repo_cache_from_url(cache_dir, _authenticated_url(token), mask=token)


def _ensure_repo_cache_from_url(cache_dir: Path, url: str, mask: str | None = None) -> None:
    """Garantiza que exista el clon disperso reutilizable en `cache_dir`,
    clonándolo UNA sola vez (requisito (2): "no re-clonar en cada
    ejecución"). `--filter=blob:none --sparse --no-checkout` no descarga
    ningún blob al clonar -- ni siquiera de la carpeta raíz -- así que
    crear el clon es barato, y `--sparse` deja listo el sparse-checkout en
    modo cone (con el patrón mínimo: solo los ficheros sueltos de la
    raíz) para que las llamadas sucesivas solo tengan que AMPLIARLO.

    Si el clon ya existe, no se vuelve a clonar: solo se refresca la URL
    remota (el token puede haber rotado entre ejecuciones -- classic PAT,
    ver §5.2 de docs/integracion_repo_reglas.md) para no dejar un token
    caducado incrustado en `.git/config`.
    """
    if (cache_dir / ".git").exists():
        _run_git(["remote", "set-url", "origin", url], cwd=cache_dir, mask=mask)
        return

    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    _run_git(
        ["clone", "--no-checkout", "--filter=blob:none", "--sparse", url, str(cache_dir)],
        cwd=cache_dir.parent,
        mask=mask,
    )
    # Windows: las rutas third-party anidadas (rules/semgrep/third-party/
    # <vendor>/<carpeta>/...) pueden superar los 260 caracteres del límite
    # clásico de Win32 dentro de un HOME ya largo -- se activa la ruta
    # larga a nivel de este repositorio local (no afecta a nada fuera de
    # `cache_dir`).
    _run_git(["config", "--local", "core.longpaths", "true"], cwd=cache_dir)
    # --skip-smudge: misma defensa que sync_rules._checkout_from_url frente
    # al "cone mode leak" (docs/integracion_repo_reglas.md §5.3) -- deja
    # TODO como punteros de texto de Git LFS al hacer checkout (nunca falla
    # por red/permisos de un fichero "vecino" que cone mode cuela sin
    # pedirlo); el contenido real solo se resuelve después, acotado a las
    # rutas que de verdad se piden, con `git lfs pull --include=...`.
    _run_git(["lfs", "install", "--local", "--skip-smudge"], cwd=cache_dir)


def _existing_sparse_patterns(cache_dir: Path) -> list[str]:
    """Qué carpetas ya están en el sparse-checkout de una ejecución
    anterior. En modo cone, `git sparse-checkout list` imprime la lista de
    directorios "legible" (lo que se le pasó a `set`/`add`), no los
    patrones internos de inclusión/exclusión -- justo lo que hace falta
    para poder AMPLIAR la lista en vez de reemplazarla."""
    if not (cache_dir / ".git").exists():
        return []
    output = _git_output(["sparse-checkout", "list"], cache_dir)
    return [line.strip() for line in output.splitlines() if line.strip()]


def _sync_worktree(cache_dir: Path, ref: str, token: str, new_patterns: list[str]) -> None:
    """Amplía el sparse-checkout con `new_patterns` (unión con lo que ya
    hubiera -- nunca un reemplazo: `sparse-checkout set` en modo cone
    excluye del working tree todo lo que no esté en la lista, así que
    olvidar la unión borraría del disco claves ya verificadas en
    ejecuciones anteriores), fija el checkout al TAG exacto de la versión
    activa, y resuelve el contenido real de Git LFS -- pero SOLO para
    `new_patterns` (lo demás no hace falta: si una clave ya cacheada
    tuviera contenido distinto en este `ref`, su hash esperado en el
    manifest también habría cambiado, y por diseño de `get_verified_rules`
    eso la habría sacado de la caché y metido en `new_patterns` -- ver el
    comentario "límite de confianza" del docstring del módulo).

    `git checkout --force` no reescribe en el working tree las rutas cuyo
    contenido no cambia entre el `ref` previamente activo y el nuevo (así
    es como Git decide qué tocar en un checkout): el contenido real ya
    resuelto por un `lfs pull` anterior para una clave sin cambios se deja
    intacto, sin volver a convertirse en puntero.
    """
    existing = set(_existing_sparse_patterns(cache_dir))
    merged = sorted(existing | set(new_patterns))
    if merged:
        _run_git(["sparse-checkout", "set", *merged], cwd=cache_dir)

    # Fetch acotado a ESE tag exacto (no "todos los tags") -- barato incluso
    # si el repo de reglas acumula muchas versiones publicadas. El refspec
    # con "+" fuerza la actualización si, por lo que sea, ya existiera un
    # ref local con ese nombre apuntando a otro commit.
    _run_git(
        ["fetch", "--no-tags", "origin", f"+refs/tags/{ref}:refs/tags/{ref}"],
        cwd=cache_dir,
        mask=token,
    )
    _run_git(["checkout", "--force", ref], cwd=cache_dir)

    if new_patterns:
        include = ",".join(f"{pattern}/**" for pattern in new_patterns)
        _run_git(["lfs", "pull", "--include", include], cwd=cache_dir)


# ---------------------------------------------------------------------------
# Estado cacheado de verificación (requisito (4)).
# ---------------------------------------------------------------------------


def _load_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {"keys": {}}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Estado cacheado corrupto/ilegible: se trata como caché vacía, NO
        # como fallo -- en el peor caso se recalculan hashes de más en esta
        # ejecución, nunca se acaba devolviendo algo sin verificar.
        return {"keys": {}}
    data.setdefault("keys", {})
    return data


def _write_state(state_path: Path, version: str, verified: dict[str, str]) -> None:
    """Actualiza el estado cacheado de forma ACUMULATIVA: solo se llama
    tras confirmar que TODO lo pedido en esta llamada verificó (fallo
    cerrado, todo-o-nada -- ver `get_verified_rules`), y solo se tocan las
    claves de `verified`; las demás, verificadas en ejecuciones
    anteriores, se conservan tal cual."""
    state = _load_state(state_path)
    keys = state.setdefault("keys", {})
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    for key_label, computed_hash in verified.items():
        keys[key_label] = {
            "hash": computed_hash,
            "verified_at": now,
            "verified_version": version,
        }
    state["last_verified_version"] = version
    state["last_verified_at"] = now

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Interfaz principal para uso como librería.
# ---------------------------------------------------------------------------


def get_verified_rules(
    languages: list[str] | None = None,
    third_party: list[str] | None = None,
    include_yara: bool = True,
    include_all_custom: bool = False,
    include_all_third_party: bool = False,
    ref: str = "latest",
) -> VerifiedRules:
    """Devuelve rutas locales YA verificadas por hash para las claves
    pedidas, descargando/verificando bajo demanda solo lo que haga falta.

    Args:
        languages: lenguajes custom a verificar, p. ej. ["python", "bash"].
            Ignorado si `include_all_custom=True`.
        third_party: entradas "<vendor>/<carpeta>", p. ej.
            ["trailofbits/rs"]. Ignorado si `include_all_third_party=True`.
        include_yara: si True (por defecto), verifica TODAS las
            categorías YARA que publique la versión activa -- nunca una
            selección parcial (requisito (6)).
        include_all_custom: si True, verifica TODOS los lenguajes custom
            publicados (ignora `languages`) -- pensado para un llamador
            que necesita el catálogo completo sin conocer de antemano qué
            lenguajes tienen carpeta `custom/` propia (p. ej.
            `static_layer.py`, ver docs/integracion_repo_reglas.md §9).
        include_all_third_party: igual que `include_all_custom`, pero
            para las carpetas third-party (ignora `third_party`).
        ref: "latest" (por defecto, la última Release publicada) o un tag
            exacto (p. ej. "v0.0.2") para fijar una versión concreta en
            vez de la más reciente.

    Raises:
        RulesClientError: falta `RULES_REPO_TOKEN`, o el manifest de la
            Release es inconsistente (tag_name != version publicada).
        RulesVerificationError: al menos una clave pedida no verificó.
            `exc.failed_keys` lista exactamente cuáles.
    """
    token = os.environ.get(ENV_TOKEN)
    if not token:
        raise RulesClientError(
            f"Falta la variable de entorno {ENV_TOKEN} (token de lectura del repo "
            f"privado de reglas {RULES_REPO})."
        )

    languages = list(languages or [])
    third_party = list(third_party or [])

    # (1) Versión activa: SIEMPRE se pregunta a la Releases API en esta
    # misma llamada -- una petición HTTP de unos pocos KB, nada de clonar
    # -- así este módulo nunca puede quedarse "convencido" de una versión
    # vieja solo porque el checkout local de watch_gate no se ha
    # actualizado (es justo la garantía que pide el problema descrito en
    # el docstring del módulo).
    tag_name, _manifest_raw, manifest = fetch_release_manifest(
        RULES_REPO, ref, token, DEFAULT_MANIFEST_ASSET
    )
    version = manifest.get("version")
    if version != tag_name:
        # No debería poder pasar (se pide la Release por ese tag exacto),
        # pero si el manifest dijera una versión distinta del tag real de
        # la Release que lo publica, es una señal de inconsistencia grave
        # en el repo de reglas -> abortar en vez de confiar en cuál de los
        # dos nombres es el "de verdad".
        raise RulesClientError(
            f"Inconsistencia en {RULES_REPO}: la Release '{tag_name}' publica un "
            f"manifest.json con version={version!r}. Abortando -- no se puede "
            "confiar en qué versión se está verificando."
        )

    langs, tp_pairs, yara_categories = _resolve_requests(
        manifest,
        languages,
        third_party,
        include_yara,
        include_all_custom=include_all_custom,
        include_all_third_party=include_all_third_party,
    )

    # (key_label, ruta relativa dentro del repo de reglas)
    requested: list[tuple[str, str]] = (
        [(_key_label_custom(lang), f"{CUSTOM_PREFIX}/{lang}") for lang in langs]
        + [
            (
                _key_label_third_party(vendor, carpeta),
                f"{THIRD_PARTY_PREFIX}/{vendor}/{carpeta}",
            )
            for vendor, carpeta in tp_pairs
        ]
        + [(_key_label_yara(category), f"{YARA_PREFIX}/{category}") for category in yara_categories]
    )

    if not requested:
        # Nada pedido (llamada "vacía"): ni red de más ni Git ni tocar el
        # estado -- se devuelve la versión activa igualmente, sin rutas.
        # `manifest` sí se propaga (no requiere verificación por hash: ver
        # docstring de VerifiedRules).
        return VerifiedRules(version=version, manifest=manifest)

    expected_hashes = _expected_hashes_by_key(manifest)
    cache_dir = repo_cache_dir()
    state_path = verified_state_file()
    state = _load_state(state_path)
    cached_keys = state.get("keys", {})

    verified: dict[str, str] = {}
    needs_fetch: list[tuple[str, str]] = []

    # (4) Caché de verificación: una clave se acepta sin tocar red/Git ni
    # recalcular su hash si YA se verificó en una ejecución anterior con
    # este MISMO hash esperado (si el manifest publicase un hash distinto
    # para esa clave -- la versión activa cambió y esa clave cambió con
    # ella -- deja de ser un "cache hit" y se re-verifica de cero) y su
    # carpeta local sigue existiendo (una caché borrada a mano nunca debe
    # poder "gastarse" como si estuviera verificada).
    for key_label, rel_path in requested:
        expected = expected_hashes.get(key_label)
        cached_entry = cached_keys.get(key_label)
        local_dir = cache_dir / rel_path
        if (
            expected is not None
            and cached_entry is not None
            and hashes_match(cached_entry.get("hash", ""), expected)
            and local_dir.is_dir()
        ):
            verified[key_label] = expected
        else:
            needs_fetch.append((key_label, rel_path))

    failed: list[str] = []

    if needs_fetch:
        _ensure_repo_cache(cache_dir, token)
        new_patterns = [rel_path for _key_label, rel_path in needs_fetch]
        _sync_worktree(cache_dir, version, token, new_patterns)

        for _key_label, rel_path in needs_fetch:
            _assert_no_lfs_pointers(cache_dir / rel_path)

        # (3) Verificación por hash, independiente por clave: nunca se
        # aborta en el primer fallo -- se recopilan TODOS los fallos para
        # poder reportarlos juntos y con detalle.
        for key_label, rel_path in needs_fetch:
            expected = expected_hashes.get(key_label)
            if expected is None:
                # El propio manifest no trae hash para esta clave -- se
                # trata como fallo de verificación (fallar cerrado), nunca
                # se activa una clave "porque sí".
                failed.append(key_label)
                continue
            try:
                computed = compute_dir_hash(cache_dir / rel_path)
            except (FileNotFoundError, ValueError):
                failed.append(key_label)
                continue
            if hashes_match(computed, expected):
                verified[key_label] = computed
            else:
                failed.append(key_label)

    if failed:
        # (5) Fallar cerrado: NI se actualiza el estado cacheado NI se
        # devuelve ninguna ruta -- ni siquiera las de las claves de
        # `verified` que sí pasaron en esta misma llamada.
        raise RulesVerificationError(sorted(failed), version=version)

    _write_state(state_path, version, verified)

    result = VerifiedRules(version=version, manifest=manifest)
    for lang in langs:
        result.custom[lang] = cache_dir / CUSTOM_PREFIX / lang
    for vendor, carpeta in tp_pairs:
        key = f"{vendor}/{carpeta}"
        result.third_party[key] = cache_dir / THIRD_PARTY_PREFIX / vendor / carpeta
    for category in yara_categories:
        result.yara[category] = cache_dir / YARA_PREFIX / category
    return result


# ---------------------------------------------------------------------------
# CLI (requisito (7)).
# ---------------------------------------------------------------------------


def _print_verified_rules(rules: VerifiedRules) -> None:
    print(f"Versión activa verificada: {rules.version}")
    for lang, path in sorted(rules.custom.items()):
        print(f"  {_key_label_custom(lang)}: {path}")
    for key, path in sorted(rules.third_party.items()):
        vendor, carpeta = key.split("/", 1)
        print(f"  {_key_label_third_party(vendor, carpeta)}: {path}")
    for category, path in sorted(rules.yara.items()):
        print(f"  {_key_label_yara(category)}: {path}")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="local_rules_client.py",
        description=(
            "Descarga y verifica por hash, bajo demanda, las reglas Semgrep/YARA "
            f"necesarias desde la última Release publicada de {RULES_REPO}. Pensado "
            "para ejecuciones LOCALES del análisis estático (fuera de CI) -- ver el "
            "docstring de este módulo para el detalle del mecanismo."
        ),
    )
    parser.add_argument(
        "--language",
        action="append",
        default=[],
        dest="languages",
        metavar="LENGUAJE",
        help="Lenguaje custom a verificar (repetible), p. ej. --language python.",
    )
    parser.add_argument(
        "--third-party",
        action="append",
        default=[],
        dest="third_party",
        metavar="VENDOR/CARPETA",
        help="Carpeta third-party a verificar (repetible), p. ej. --third-party trailofbits/rs.",
    )
    parser.add_argument(
        "--all-yara",
        action="store_true",
        help="Verifica TODAS las categorías YARA publicadas (nunca una selección parcial).",
    )
    parser.add_argument(
        "--all-languages",
        action="store_true",
        help="Verifica TODOS los lenguajes custom publicados (ignora --language).",
    )
    parser.add_argument(
        "--all-third-party",
        action="store_true",
        help="Verifica TODAS las carpetas third-party publicadas (ignora --third-party).",
    )
    parser.add_argument(
        "--ref",
        default="latest",
        help="'latest' (por defecto, la última Release publicada) o un tag exacto, p. ej. v0.0.2.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    nothing_requested = not (
        args.languages
        or args.third_party
        or args.all_yara
        or args.all_languages
        or args.all_third_party
    )
    if nothing_requested:
        print(
            "ERROR: no se pidió ninguna clave -- usa --language / --third-party / --all-yara / "
            "--all-languages / --all-third-party.",
            file=sys.stderr,
        )
        return 2

    try:
        rules = get_verified_rules(
            languages=args.languages,
            third_party=args.third_party,
            include_yara=args.all_yara,
            include_all_custom=args.all_languages,
            include_all_third_party=args.all_third_party,
            ref=args.ref,
        )
    except RulesVerificationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except RulesClientError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 -- CLI: nunca un fallo silencioso, siempre exit != 0
        print(f"ERROR inesperado: {exc}", file=sys.stderr)
        return 1

    _print_verified_rules(rules)
    return 0


if __name__ == "__main__":
    sys.exit(main())
