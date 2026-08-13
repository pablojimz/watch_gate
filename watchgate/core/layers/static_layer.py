"""Capa de análisis estático (spec §4).

Ejecuta Semgrep + YARA sobre los parches de código modificados
(`diff_hunk`) y combina ambos con un único `max()` (spec §4 paso 4: nunca
sumar), bajo el mismo `layer_name="static"` -- son la MISMA capa, con el
mismo peso en `.watchgate.yml` (`static: 0.25  # Semgrep / YARA`).

- **Semgrep**, específico del lenguaje del archivo: reglas propias
  (`rules/semgrep/custom/<lenguaje>`), de terceros relevantes para ese
  lenguaje (`rules/semgrep/third-party/<vendor>/<carpeta>`) y de patrones
  genéricos (`rules/semgrep/custom/regex`, secretos hardcodeados etc.).
- **YARA**, con independencia del lenguaje (un webshell puede llevar
  cualquier extensión, o ninguna): TODAS las categorías publicadas
  siempre (`rules/yara/<categoria>/`, sin selección parcial -- requisito
  explícito del diseño), usando el `risk_score` que cada regla ya trae en
  sus propios metadatos (`meta.risk_score`, calculado en el repo de
  reglas: `0.45*severity + 0.30*confidence + 0.25*exploitability`).

Ambas familias de reglas vienen del MISMO repo privado de reglas
(`pablojimz/Repo-reglas-SEMGREP-y-YARA`) y se sincronizan/verifican por
hash con el mismo mecanismo -- ver docs/integracion_repo_reglas.md.

Resolución del directorio de reglas (`_get_rules_dir`), en orden:
0. Verificación bajo demanda contra la ÚLTIMA versión publicada
   (`scripts/local_rules_client.get_verified_rules`), si la variable de
   entorno RULES_REPO_TOKEN está configurada en el proceso -- ver
   docs/integracion_repo_reglas.md §9. Desacopla "tener este checkout de
   watch_gate actualizado" de "la capa estática usa las reglas
   correctas": cada `analyze()` pregunta a la Releases API cuál es la
   versión activa y descarga/verifica bajo demanda lo que le falte (con
   caché local, así que en la práctica solo hay trabajo real de red/Git
   cuando de verdad se publicó una versión nueva). Si este paso falla por
   cualquier motivo (sin token, sin red, verificación fallida) se
   registra y se cae a los pasos 1-4 SIN abortar el análisis -- nunca es
   la única fuente de reglas disponible.
1. Override explícito por parámetro de constructor.
2. Variable de entorno WATCHGATE_SEMGREP_RULES_DIR.
3. Directorio local del proyecto `rules/semgrep/` -- esta es la ruta que
   pueblan y verifican por hash .github/workflows/sync-rules.yml y
   reconcile-rules.yml (ver docs/integracion_repo_reglas.md); en este
   propio repo SIEMPRE debería resolverse aquí (o en el paso 0, si el
   token está disponible en el entorno).
4. Caché local persistente en .watchgate/rules_cache/ (TTL 24h, clon
   directo de GitHub sin ninguna verificación de hash). Es un ÚLTIMO
   RECURSO pensado para un consumidor externo que instale `watchgate`
   como paquete sin el checkout de reglas ya sincronizado -- nunca
   debería alcanzarse en el análisis de PRs de este propio repo, y si se
   alcanza, se loggea como warning explícito porque implica ejecutar
   reglas sin pasar por la verificación de integridad.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml
import yara

from watchgate.core.layers._shared import scan_diff_hunk_for_suspicious_patterns
from watchgate.core.layers.base import AnalysisLayer, register_layer
from watchgate.core.models import (
    Confidence,
    FileChange,
    FileStatus,
    Finding,
    LayerResult,
    NormalizedDiff,
    RiskCategory,
    ThreatNature,
    compute_dominant_threat_nature,
)

logger = logging.getLogger("watchgate.static")

# URL del repositorio externo de reglas Semgrep
SEMGREP_RULES_REPO_URL = "https://github.com/pablojimz/Repo-reglas-SEMGREP-y-YARA.git"

# Puntuación de riesgo por severidad oficial de Semgrep (spec §4)
SEVERITY_SCORE: dict[str, int] = {
    "INFO": 10,
    "WARNING": 30,
    "ERROR": 60,
}

# Tiempo TTL (24 horas) para verificación de actualización del repo de reglas
_CACHE_TTL_SECONDS = 86400
_GIT_TIMEOUT_SECONDS = 5.0

# Timeout del PRIMER clon completo (caso 5 de _get_rules_dir, "último
# recurso"). 15s bastaba mientras las reglas eran YAML/.yar en texto plano,
# pero el repo las versiona con Git LFS -- cada fichero es un objeto LFS
# aparte que se descarga por separado durante el checkout, y con ~800
# reglas ese primer clon puede tardar bastante más de 15s sin que nada
# esté realmente roto (verificado en vivo contra un Engine API real:
# tardó ~35s desde contenedor limpio). Un timeout corto no solo falla la
# petición en curso -- ver _cleanup_partial_clone para por qué además deja
# el proceso "envenenado" para las peticiones siguientes.
_INITIAL_CLONE_TIMEOUT_SECONDS = 90.0

# Timeout de CADA invocación de Semgrep en _run_semgrep_on_file (un
# subprocess por fichero del diff). 20s basta en caliente (medido en vivo:
# ~7s con las reglas ya resueltas y en caché de página del SO), pero
# inmediatamente después del primer clon en frío (ver
# _INITIAL_CLONE_TIMEOUT_SECONDS) -- ficheros de regla recién escritos por
# el checkout de Git LFS, sin nada calentado en caché de disco/SO -- se
# midió en vivo un TimeoutExpired real a los 20.0s exactos contra un Engine
# API recién arrancado. El resultado no era "0 hallazgos", era una
# excepción silenciada por el `except Exception` de más abajo, que
# _run_semgrep_on_file trata igual que "esta regla no aplica" -- la
# petición entera respondía 200 OK con la capa `static` en 0 sin ningún
# indicio de que en realidad ni siquiera había terminado de analizar.
_SEMGREP_SUBPROCESS_TIMEOUT_SECONDS = 60.0

# Puntuación de riesgo si una regla YARA coincide pero, por lo que sea, no
# trae su propio meta.risk_score (no debería pasar con las reglas
# generadas por el repo de reglas, pero es defensivo ante una regla
# externa mal formada) -- se usa un valor alto porque el catálogo YARA
# aquí es todo de detección de malware/webshells, nunca un simple aviso.
_YARA_DEFAULT_RISK_SCORE = 60

# Caché de reglas YARA compiladas, con vida de PROCESO (no de disco, a
# diferencia de la caché de git de _get_rules_dir): compilar ~700 reglas
# YARA de golpe no es gratis, y dentro de una misma ejecución de
# `analyze()` se compila una sola vez y se reutiliza para todos los
# ficheros del diff. Cada proceso de `watchgate` (CLI, GitHub Action) es
# de usar-y-tirar, así que no hay riesgo de servir reglas obsoletas tras
# una resincronización -- un proceso nuevo siempre recompila.
_yara_rules_cache: dict[str, yara.Rules | None] = {}

# Caché (misma vida de PROCESO que _yara_rules_cache) del mapeo
# id-de-regla -> `finding_type` declarado en el propio YAML de cada regla
# Semgrep ("vulnerability" | "malicious" | "needs_review" | "unclassified",
# ver rules/manifest.json:finding_type_summary), construido parseando los
# ficheros de reglas directamente en vez de reinferir la clasificación a
# mano -- ver StaticLayer._get_semgrep_finding_types para el porqué (no
# todas las reglas lo declaran en el mismo bloque). Sirve para que, a
# partir del `check_id` de un hallazgo, se use la clasificación que el
# propio autor de la regla ya decidió, en vez de la heurística de
# _infer_threat_nature_from_semgrep (que se conserva solo como fallback
# para reglas sin `finding_type` declarado, ver _run_semgrep_on_file).
_semgrep_finding_type_cache: dict[str, dict[str, str]] = {}

# Categoría de reglas custom/ que se aplica SIEMPRE, con independencia del
# lenguaje detectado (patrones de secretos hardcodeados, cadenas de
# conexión, etc. -- no son específicos de un lenguaje).
_ALWAYS_ON_CUSTOM_CATEGORY = "regex"

# Mapeo EXPLÍCITO (a mano, nunca adivinado por coincidencia de nombre) de
# lenguaje detectado -> carpetas de third-party relevantes. El repo de
# reglas deja claro que <carpeta> de third-party es un namespace
# independiente que NO siempre coincide con el nombre del lenguaje (p. ej.
# trailofbits/rs son reglas de Rust) -- por eso esta tabla se mantiene a
# mano en vez de intentar `carpeta == language`. Se excluyen a propósito
# los paquetes que no son de un lenguaje concreto (opengrep/generic,
# opengrep/problem-based-packs, trailofbits/generic, 0xdea/noisy): este
# análisis es por-fichero, y esos paquetes no están pensados para eso.
THIRD_PARTY_LANGUAGE_MAP: dict[str, list[tuple[str, str]]] = {
    "python": [("trailofbits", "python"), ("opengrep", "python")],
    "javascript": [("trailofbits", "javascript"), ("opengrep", "javascript")],
    "typescript": [("opengrep", "typescript")],
    "java": [("opengrep", "java"), ("trailofbits", "jvm")],
    "c": [("0xdea", "c")],
    "go": [("elttam", "go"), ("opengrep", "go"), ("trailofbits", "go")],
    "bash": [("opengrep", "bash")],
    "yaml": [("elttam", "yaml"), ("opengrep", "yaml"), ("trailofbits", "yaml")],
    "html": [("opengrep", "html")],
    "ruby": [("opengrep", "ruby"), ("trailofbits", "ruby")],
    "csharp": [("opengrep", "csharp")],
    "clojure": [("opengrep", "clojure")],
    "ocaml": [("opengrep", "ocaml")],
    "php": [("opengrep", "php")],
    "json": [("opengrep", "json")],
    "rust": [("trailofbits", "rs")],
    "swift": [("opengrep", "swift"), ("trailofbits", "swift")],
    "kotlin": [("opengrep", "kotlin")],
    "scala": [("opengrep", "scala")],
    "solidity": [("opengrep", "solidity")],
    "terraform": [("opengrep", "terraform"), ("trailofbits", "hcl")],
}


def _infer_threat_nature_from_semgrep(
    finding_extra: dict[str, Any] | None, rule_id: str
) -> ThreatNature:
    """Heurística de RESPALDO cuando no hay `finding_type` declarado para la
    regla (rule_id ausente del mapeo de _get_semgrep_finding_types -- p. ej.
    reglas externas no generadas por el repo de reglas, o clasificadas como
    "needs_review"/"unclassified"). El camino preferente es el `finding_type`
    explícito de options: ver _run_semgrep_on_file."""
    if not isinstance(finding_extra, dict):
        finding_extra = {}

    metadata = finding_extra.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    cat = str(metadata.get("category", "")).lower()
    nature = str(metadata.get("threat_nature", "")).lower()
    subcategory = str(metadata.get("subcategory", "")).lower()

    malicious_keywords = {
        "malware",
        "backdoor",
        "exfiltration",
        "obfuscation",
        "trojan",
        "c2",
        "persistence",
        "supply-chain-attack",
    }

    if nature in ("malicioso", "malicious"):
        return ThreatNature.MALICIOUS
    if nature in ("vulnerabilidad", "vulnerability"):
        return ThreatNature.VULNERABILITY

    rule_lower = rule_id.lower()
    # Coincidencia por palabra completa, no por substring: "c2" es lo
    # bastante corto para matchear por accidente dentro de un id/categoría
    # de regla que no tenga nada que ver (p. ej. algo con "c2c" o "src2").
    keyword_pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(kw) for kw in malicious_keywords) + r")\b"
    )
    if (
        keyword_pattern.search(cat)
        or keyword_pattern.search(subcategory)
        or keyword_pattern.search(rule_lower)
    ):
        return ThreatNature.MALICIOUS

    return ThreatNature.VULNERABILITY


def _finding_type_of_rule(rule: dict[str, Any]) -> str | None:
    """Extrae `finding_type` de una regla ya parseada, priorizando
    `metadata:` (bloque que Semgrep sí reenvía en el JSON de cada
    hallazgo) sobre `options:` (donde lo declaran las 3 reglas heredadas
    que necesitan ese bloque por otro motivo -- ver docstring de
    StaticLayer._get_semgrep_finding_types)."""
    for block_name in ("metadata", "options"):
        block = rule.get(block_name, {})
        if not isinstance(block, dict):
            continue
        finding_type = block.get("finding_type")
        if isinstance(finding_type, str) and finding_type:
            return finding_type.strip().lower()
    return None


def _handle_remove_read_only(func: Any, path: str, exc_info: Any) -> None:
    """Error handler para shutil.rmtree que cambia permisos de solo lectura y reintenta."""
    if func in (os.unlink, shutil.rmtree) and issubclass(exc_info[0], PermissionError):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    else:
        raise exc_info[1]


# Nombre de la variable de entorno que autentica contra el repo privado de
# reglas (mismo secret que usan .github/workflows/sync-rules.yml /
# reconcile-rules.yml, ver docs/integracion_repo_reglas.md §5.2). Se
# comprueba su presencia ANTES de intentar importar/llamar a
# local_rules_client -- sin ella no hay forma de preguntar a la Releases
# API, así que ni vale la pena el import.
_RULES_REPO_TOKEN_ENV = "RULES_REPO_TOKEN"

# Charset seguro para usar la versión activa ("v0.0.3") como nombre de
# subdirectorio de la vista local de reglas verificadas -- defensivo, no
# una comprobación de seguridad crítica (esa ya la hace
# local_rules_client, letra a letra, sobre cada clave ANTES de tocar
# disco/red); aquí solo evita que un valor inesperado rompa la ruta.
_UNSAFE_VERSION_PATH_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def _sanitize_version_for_path(version: str) -> str:
    cleaned = _UNSAFE_VERSION_PATH_CHARS.sub("_", version.strip())
    return cleaned or "unknown"


def _import_local_rules_client() -> Any | None:
    """Importa `scripts/local_rules_client.py` bajo demanda -- nunca al
    cargar este módulo. `scripts/` no es un paquete instalado: un
    consumidor externo que instale `watchgate` como paquete pip puede no
    traer ese directorio, y `_get_verified_rules_dir` debe degradar a los
    pasos existentes de `_get_rules_dir` en ese caso, sin romper el import
    de `static_layer.py` en sí."""
    scripts_dir = Path(__file__).resolve().parents[3] / "scripts"
    if not (scripts_dir / "local_rules_client.py").exists():
        return None
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    try:
        import local_rules_client  # type: ignore[import-not-found]
    except ImportError:
        return None
    return local_rules_client


@register_layer
class StaticLayer(AnalysisLayer):
    """Capa de análisis estático que ejecuta Semgrep sobre los parches modificados."""

    name: str = "static"

    def __init__(self, rules_dir_override: str | Path | None = None) -> None:
        self.rules_dir_override = Path(rules_dir_override) if rules_dir_override else None

    def _refresh_rules_view_entry(self, src: Path, dst: Path) -> None:
        """Deja `dst` apuntando al contenido YA VERIFICADO de `src`.

        Se intenta un symlink de directorio primero (barato, sin copiar
        nada); si la plataforma/permisos no lo permiten (p. ej. Windows
        sin "Developer Mode" ni privilegios de administrador -- el caso
        habitual en una máquina de desarrollo), se cae a una copia real:
        el contenido de reglas es texto plano, unos pocos MB en total, así
        que copiar es aceptable como respaldo."""
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_symlink():
            dst.unlink()
        elif dst.is_dir():
            shutil.rmtree(dst, onerror=_handle_remove_read_only)
        elif dst.exists():
            dst.unlink()
        try:
            os.symlink(src, dst, target_is_directory=True)
        except OSError:
            shutil.copytree(src, dst)

    def _sync_rules_view(self, view_root: Path, rules: Any) -> None:
        """Remapea las rutas verificadas devueltas por
        `local_rules_client.get_verified_rules()` (que son agnósticas de
        cualquier convención de `watch_gate`, ver docstring de ese módulo)
        a la MISMA convención de rutas que el resto de este fichero espera
        bajo `view_root`: `rules/semgrep/custom/<lenguaje>`,
        `rules/semgrep/third-party/<vendor>/<carpeta>`,
        `rules/yara/<categoria>` -- análogo al remapeo que hace
        `sync_rules._apply_verified_content` al comitear sobre el árbol
        git de watch_gate, pero apuntando a una caché local fuera de git."""
        for lang, src in rules.custom.items():
            dst = view_root / "rules" / "semgrep" / "custom" / lang
            self._refresh_rules_view_entry(src, dst)
        for key, src in rules.third_party.items():
            vendor, carpeta = key.split("/", 1)
            dst = view_root / "rules" / "semgrep" / "third-party" / vendor / carpeta
            self._refresh_rules_view_entry(src, dst)
        for category, src in rules.yara.items():
            dst = view_root / "rules" / "yara" / category
            self._refresh_rules_view_entry(src, dst)

    def _get_verified_rules_dir(self) -> Path | None:
        """Paso 0 de `_get_rules_dir`: verifica contra la ÚLTIMA versión
        publicada del repo de reglas (`local_rules_client.get_verified_rules`,
        catálogo completo: todos los lenguajes custom, todas las carpetas
        third-party, todas las categorías YARA) y materializa una vista
        local con ese contenido YA verificado -- ver docs/integracion_repo_reglas.md §9.

        Nunca lanza: cualquier fallo (sin token, sin red, verificación de
        integridad fallida) se registra y devuelve None, para que
        `_get_rules_dir` caiga a los pasos 1-4 existentes -- este paso
        nunca debe ser la única fuente de reglas disponible.

        La vista se materializa bajo un subdirectorio con el NOMBRE de la
        versión activa (`rules-view/<version>/...`, no `rules-view/...` a
        secas): así, si este proceso vive más de un `analyze()` (p. ej. la
        Engine API o el dashboard backend, de larga duración) y la versión
        activa cambia entre dos llamadas, la ruta resuelta cambia con
        ella, y con eso basta para que las cachés de PROCESO existentes
        (`_yara_rules_cache`, `_semgrep_finding_type_cache`, indexadas por
        la ruta resuelta) dejen de servir contenido de la versión anterior
        sin tener que tocar esas cachés en sí.
        """
        if not os.environ.get(_RULES_REPO_TOKEN_ENV):
            # Sin token no hay forma de preguntar a la Releases API. Es
            # una configuración legítima (p. ej. un consumidor externo, o
            # el workflow de análisis de PRs de este propio repo, que hoy
            # NO recibe este secret -- solo lo reciben sync-rules.yml /
            # reconcile-rules.yml, ver docs/integracion_repo_reglas.md §9)
            # -- se cae en silencio a los pasos existentes.
            return None

        local_rules_client = _import_local_rules_client()
        if local_rules_client is None:
            return None

        try:
            rules = local_rules_client.get_verified_rules(
                include_all_custom=True, include_all_third_party=True, include_yara=True
            )
        except local_rules_client.RulesClientError as exc:
            logger.info(
                "No se pudo verificar la versión activa de las reglas (%s); "
                "se usa el checkout local.",
                exc,
            )
            return None
        except local_rules_client.RulesVerificationError as exc:
            logger.error(
                "Verificación de integridad de reglas fallida (%s); se usa el "
                "último checkout local ya verificado.",
                exc,
            )
            return None
        except Exception as exc:  # noqa: BLE001 -- nunca debe abortar el análisis por esto
            logger.warning(
                "Fallo inesperado verificando la versión activa de las reglas "
                "(%r); se usa el checkout local.",
                exc,
            )
            return None

        view_root = (
            local_rules_client.repo_cache_dir().parent
            / "rules-view"
            / _sanitize_version_for_path(rules.version)
        )
        try:
            self._sync_rules_view(view_root, rules)
        except OSError as exc:
            logger.warning(
                "No se pudo materializar la vista local de reglas verificadas "
                "(%r); se usa el checkout local.",
                exc,
            )
            return None

        logger.info(
            "Capa estática usando reglas verificadas de la versión activa %s (%s).",
            rules.version,
            view_root,
        )
        return view_root  # type: ignore[no-any-return]

    def _get_rules_dir(self) -> Path | None:
        """Obtiene la ruta al directorio de reglas Semgrep con sincronización inteligente.

        Prioridad de resolución:
        0. Verificación bajo demanda contra la última versión publicada
           (ver `_get_verified_rules_dir`), si RULES_REPO_TOKEN está en el
           entorno.
        1. Override explícito por parámetro de constructor.
        2. Variable de entorno WATCHGATE_SEMGREP_RULES_DIR.
        3. Directorio local del proyecto rules/semgrep/ si contiene reglas.
        4. Caché local persistente en .watchgate/rules_cache/ con TTL de 24h y fallback offline.
        """
        # 0. Verificación bajo demanda contra la última versión publicada
        verified_dir = self._get_verified_rules_dir()
        if verified_dir is not None:
            return verified_dir

        # 1. Override por constructor
        if self.rules_dir_override and self.rules_dir_override.exists():
            return self.rules_dir_override

        # 2. Variable de entorno
        env_rules_dir = os.environ.get("WATCHGATE_SEMGREP_RULES_DIR")
        if env_rules_dir:
            env_path = Path(env_rules_dir)
            if env_path.exists():
                return env_path

        # 3. Directorio del paquete/repositorio WatchGate instalado
        package_root = Path(__file__).resolve().parents[3]
        pkg_rules_dir = package_root / "rules" / "semgrep"
        if pkg_rules_dir.exists() and any(pkg_rules_dir.iterdir()):
            return package_root

        # 4. Directorio local del proyecto actual
        local_rules_dir = Path("rules/semgrep")
        if local_rules_dir.exists() and any(local_rules_dir.iterdir()):
            return Path(".")

        # 5. Caché persistente en .watchgate/rules_cache/ -- ÚLTIMO RECURSO.
        logger.info(
            "rules/semgrep/ no está disponible localmente -- usando la caché de reglas "
            "en .watchgate/rules_cache/ (ver docs/integracion_repo_reglas.md)."
        )
        cache_base = Path.home() / ".watchgate" / "rules_cache"
        repo_name = "Repo-reglas-SEMGREP-y-YARA"
        cached_repo_dir = cache_base / repo_name
        timestamp_file = cache_base / ".last_updated"

        now = time.time()
        should_check_remote = False

        if cached_repo_dir.exists():
            # Si pasaron más de 24 horas o se fuerza por entorno, se marca comprobación remota
            if os.environ.get("WATCHGATE_UPDATE_RULES", "").lower() in ("true", "1"):
                should_check_remote = True
            elif timestamp_file.exists():
                try:
                    last_check = float(timestamp_file.read_text(encoding="utf-8").strip())
                    if now - last_check >= _CACHE_TTL_SECONDS:
                        should_check_remote = True
                except Exception:  # noqa: BLE001
                    should_check_remote = True
            else:
                should_check_remote = True

            if not should_check_remote:
                # Caché local vigente (0 ms sobrecoste de red)
                return cached_repo_dir

            # Intentar comprobación ligera git ls-remote / pull
            try:
                logger.info("Comprobando actualizaciones remotas del repositorio de reglas...")
                cache_base.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["git", "fetch", "--depth=1"],
                    cwd=str(cached_repo_dir),
                    capture_output=True,
                    timeout=_GIT_TIMEOUT_SECONDS,
                    check=False,
                )
                timestamp_file.write_text(str(now), encoding="utf-8")
                return cached_repo_dir
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "No se pudo actualizar el repo de reglas por red (%r). Usando caché local.", exc
                )
                return cached_repo_dir

        # Si la caché local no existe, clonar por primera vez
        try:
            cache_base.mkdir(parents=True, exist_ok=True)
            logger.info("Clonando repositorio de reglas Semgrep en %s", cached_repo_dir)
            res = subprocess.run(
                ["git", "clone", "--depth", "1", SEMGREP_RULES_REPO_URL, str(cached_repo_dir)],
                capture_output=True,
                text=True,
                timeout=_INITIAL_CLONE_TIMEOUT_SECONDS,
                check=False,
            )
            if res.returncode == 0 and cached_repo_dir.exists():
                timestamp_file.write_text(str(now), encoding="utf-8")
                return cached_repo_dir
            logger.warning("Fallo al clonar reglas Semgrep: %s", res.stderr)
            self._cleanup_partial_clone(cached_repo_dir)
            return None
        except subprocess.TimeoutExpired:
            logger.warning(
                "Timeout (%.0fs) clonando el repo de reglas Semgrep -- se descarta el "
                "clon parcial (ver _cleanup_partial_clone) para que el siguiente intento "
                "arranque limpio en vez de heredar ficheros de reglas a medio resolver.",
                _INITIAL_CLONE_TIMEOUT_SECONDS,
            )
            self._cleanup_partial_clone(cached_repo_dir)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error al clonar repositorio de reglas Semgrep: %r", exc)
            self._cleanup_partial_clone(cached_repo_dir)
            return None

    def _cleanup_partial_clone(self, cached_repo_dir: Path) -> None:
        """Borra un clon parcial/roto tras un fallo o timeout del paso 5 de
        `_get_rules_dir` (último recurso).

        Hallazgo real de un E2E contra un Engine API real (no hipotético):
        sin esto, un timeout a mitad de clonar deja `cached_repo_dir`
        existente pero con contenido a medio resolver -- con las reglas
        versionadas en Git LFS, eso significa ficheros de regla que siguen
        siendo el puntero LFS en texto plano en vez del YAML/.yar real (Semgrep
        los rechaza con "was not a mapping"). La siguiente llamada a
        `_get_rules_dir` ve `cached_repo_dir.exists() == True` y toma la rama
        "la caché ya existe" (más arriba), que solo hace un `git fetch`
        ligero -- nunca vuelve a comprobar integridad ni fuerza un clon
        completo. Peor aún: `_get_semgrep_finding_types`/
        `_get_compiled_yara_rules` cachean su resultado (vacío o incompleto)
        en memoria de PROCESO, indexado solo por la ruta resuelta -- una vez
        envenenado, ese proceso nunca vuelve a intentarlo, aunque el
        directorio en disco se complete por su cuenta más tarde. Borrar el
        clon parcial aquí fuerza un clon limpio de verdad en el siguiente
        intento."""
        if cached_repo_dir.exists():
            try:
                shutil.rmtree(cached_repo_dir, onerror=_handle_remove_read_only)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "No se pudo limpiar el clon parcial de reglas en %s (%r) -- puede "
                    "quedar contenido a medio resolver hasta que se recree el contenedor.",
                    cached_repo_dir,
                    exc,
                )

    def _detect_language(self, file_path: str) -> str | None:
        """Infiere el lenguaje del archivo para mapearlo contra las reglas Semgrep.

        Cubre los 17 lenguajes de rules/semgrep/custom/ más los que solo
        tienen reglas de terceros (kotlin, scala, solidity, terraform) --
        ver THIRD_PARTY_LANGUAGE_MAP.
        """
        basename = os.path.basename(file_path).lower()
        # Dockerfile no sigue convención de extensión: puede ser
        # literalmente "Dockerfile", "Dockerfile.prod", o "algo.dockerfile".
        if (
            basename == "dockerfile"
            or basename.startswith("dockerfile.")
            or basename.endswith(".dockerfile")
        ):
            return "dockerfile"

        extension = os.path.splitext(file_path)[1].lower()
        language_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".java": "java",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".go": "go",
            ".sh": "bash",
            ".bash": "bash",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".html": "html",
            ".rb": "ruby",
            ".cs": "csharp",
            ".clj": "clojure",
            ".cljs": "clojure",
            ".cljc": "clojure",
            ".ml": "ocaml",
            ".mli": "ocaml",
            ".php": "php",
            ".ps1": "powershell",
            ".psm1": "powershell",
            ".json": "json",
            ".rs": "rust",
            ".swift": "swift",
            ".kt": "kotlin",
            ".kts": "kotlin",
            ".scala": "scala",
            ".sol": "solidity",
            ".tf": "terraform",
            ".hcl": "terraform",
        }
        return language_map.get(extension)

    def _get_semgrep_finding_types(self, rules_dir: Path) -> dict[str, str]:
        """Construye (con caché de proceso) el mapeo id-de-regla ->
        `finding_type` leyendo directamente los YAML de
        rules/semgrep/**/*.yml(.yaml).

        La inmensa mayoría de las reglas (comprobado empíricamente sobre el
        árbol actual: 775 de 803) declaran `finding_type` bajo `metadata:`,
        que Semgrep SÍ reenvía tal cual en `extra.metadata` de cada
        hallazgo -- para esas se podría leer directamente del JSON de
        salida. Pero un puñado de reglas antiguas (`languages: [generic]`,
        que ya necesitan un bloque `options:` para
        `generic_ellipsis_max_span`) lo declaran ahí en su lugar, y
        `options:` NO se reenvía en el JSON de Semgrep -- así que se
        prioriza `metadata.finding_type` y se usa `options.finding_type`
        como alternativa, para que el resultado no dependa de en qué
        bloque haya elegido declararlo cada regla."""
        semgrep_root = rules_dir / "rules" / "semgrep"
        cache_key = (
            str(semgrep_root.resolve()) if semgrep_root.exists() else f"missing:{semgrep_root}"
        )
        if cache_key in _semgrep_finding_type_cache:
            return _semgrep_finding_type_cache[cache_key]

        finding_types: dict[str, str] = {}
        if not semgrep_root.exists():
            _semgrep_finding_type_cache[cache_key] = finding_types
            return finding_types

        for pattern in ("*.yml", "*.yaml"):
            for rule_file in semgrep_root.rglob(pattern):
                try:
                    doc = yaml.safe_load(rule_file.read_text(encoding="utf-8"))
                except Exception as exc:  # noqa: BLE001
                    logger.debug("No se pudo parsear %s como YAML de reglas: %r", rule_file, exc)
                    continue

                if not isinstance(doc, dict):
                    continue
                for rule in doc.get("rules", []) or []:
                    if not isinstance(rule, dict):
                        continue
                    rule_id = rule.get("id")
                    finding_type = _finding_type_of_rule(rule)
                    if rule_id and finding_type:
                        finding_types[str(rule_id)] = finding_type

        _semgrep_finding_type_cache[cache_key] = finding_types
        return finding_types

    def _build_semgrep_config_paths(self, language: str, rules_dir: Path) -> list[str]:
        """Construye la lista de `--config=...` de Semgrep para `language`.

        Determinista: dos ficheros del MISMO `language` producen siempre la
        MISMA lista -- por eso es seguro agrupar varios ficheros del mismo
        lenguaje en una única invocación de Semgrep (ver
        `_run_semgrep_on_files`, que depende de esta propiedad).

        Estrategia 1: rules/semgrep/custom/<language>
        Estrategia 1b: rules/semgrep/custom/regex (patrones genéricos,
          siempre se aplican con independencia del lenguaje)
        Estrategia 1c: rules/semgrep/third-party/<vendor>/<carpeta>
          relevantes para <language> (ver THIRD_PARTY_LANGUAGE_MAP)
        Estrategia 2: rules/semgrep/watchgate.yml
        Estrategia 3: raiz del directorio de reglas (si nada de lo
          anterior existe -- último recurso, escanea todo)
        """
        config_paths: list[str] = []
        semgrep_root = rules_dir / "rules" / "semgrep"

        custom_lang_dir = semgrep_root / "custom" / language
        if custom_lang_dir.exists():
            config_paths.append(f"--config={custom_lang_dir}")

        if language != _ALWAYS_ON_CUSTOM_CATEGORY:
            custom_regex_dir = semgrep_root / "custom" / _ALWAYS_ON_CUSTOM_CATEGORY
            if custom_regex_dir.exists():
                config_paths.append(f"--config={custom_regex_dir}")

        for vendor, carpeta in THIRD_PARTY_LANGUAGE_MAP.get(language, []):
            third_party_dir = semgrep_root / "third-party" / vendor / carpeta
            if third_party_dir.exists():
                config_paths.append(f"--config={third_party_dir}")

        watchgate_yml = semgrep_root / "watchgate.yml"
        if watchgate_yml.exists():
            config_paths.append(f"--config={watchgate_yml}")

        if not config_paths:
            # Último recurso: si el árbol `rules/semgrep` existe pero ninguna
            # subcarpeta concreta aplicó (p. ej. un checkout a medio
            # sincronizar al que solo le falta `custom/regex`), acotar el
            # escaneo a ese árbol -- nunca a `rules_dir` a secas, que en el
            # caso 3 de `_get_rules_dir` es literalmente `Path(".")` (la
            # raíz del repo completo) y escanearía con Semgrep cualquier
            # YAML con forma de regla en todo el proyecto, no solo las
            # reglas de WatchGate.
            if semgrep_root.exists():
                config_paths.append(f"--config={semgrep_root}")
            elif rules_dir.exists():
                config_paths.append(f"--config={rules_dir}")

        return config_paths

    def _resolve_semgrep_bin(self) -> str:
        semgrep_bin = shutil.which("semgrep")
        if semgrep_bin:
            return semgrep_bin
        venv_semgrep = Path(sys.prefix) / "bin" / "semgrep"
        if venv_semgrep.exists():
            return str(venv_semgrep)
        return "semgrep"

    def _run_semgrep_on_files(
        self, temp_file_paths: list[str], language: str, rules_dir: Path
    ) -> dict[str, list[dict[str, Any]]]:
        """Ejecuta Semgrep UNA SOLA VEZ sobre varios ficheros temporales del
        MISMO `language` (mismo `_build_semgrep_config_paths`, determinista),
        en vez de un subproceso por fichero.

        Medido en vivo (prototipo aislado, mismo entorno que producción,
        mismo repo de reglas real: ~800 reglas repartidas en custom +
        third-party): el coste dominante de cada invocación de Semgrep NO es
        escanear un fichero más, es COMPILAR el conjunto de reglas desde
        cero -- Semgrep no cachea reglas compiladas entre invocaciones
        separadas del CLI, y ese coste de arranque (15-40s por invocación)
        es prácticamente independiente de cuántos ficheros se le pasen
        DENTRO de esa invocación. Agrupar por lenguaje (mismo `--config`,
        así que Semgrep hace exactamente el mismo trabajo de matching que
        haría por separado) reduce el NÚMERO de invocaciones de "una por
        fichero" a "una por lenguaje distinto presente en el diff": 2
        ficheros Python, medido en vivo, 82s -> 29s.

        Devuelve `temp_file_path -> lista de hallazgos`, usando el campo
        `path` que el propio JSON de Semgrep reporta por hallazgo
        (confirmado en vivo: Semgrep etiqueta cada resultado con la ruta
        EXACTA del fichero de origen, sin normalizar, incluso con varios
        ficheros en la misma invocación) para saber a cuál de los ficheros
        pasados pertenece cada uno -- sin esto, los hallazgos de varios
        ficheros llegarían mezclados sin forma de distinguirlos.

        Trade-off aceptado: un timeout aquí pierde los hallazgos de TODOS
        los ficheros del grupo, no solo de uno (antes, un timeout solo
        afectaba al fichero que se estaba analizando en ese momento) -- ver
        el WARNING más abajo, que ahora lo dice explícitamente.
        """
        results: dict[str, list[dict[str, Any]]] = {p: [] for p in temp_file_paths}
        if not temp_file_paths:
            return results

        config_paths = self._build_semgrep_config_paths(language, rules_dir)
        if not config_paths:
            return results

        semgrep_bin = self._resolve_semgrep_bin()
        command = [semgrep_bin, "--json", "--quiet", *temp_file_paths, *config_paths]

        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=_SEMGREP_SUBPROCESS_TIMEOUT_SECONDS,
                check=False,
                encoding="utf-8",
                errors="replace",
            )
            if process.returncode not in (0, 1):  # Semgrep retorna 1 si encuentra hallazgos
                logger.debug("Semgrep retornó código %d: %s", process.returncode, process.stderr)

            if not process.stdout.strip():
                return results

            semgrep_output = json.loads(process.stdout)
            declared_finding_types = self._get_semgrep_finding_types(rules_dir)
            for finding in semgrep_output.get("results", []):
                finding_path = finding.get("path")
                if finding_path not in results:
                    # Defensivo -- no debería pasar (Semgrep solo puede
                    # reportar sobre los ficheros que le pasamos), pero si
                    # pasa, se agrupa aparte en vez de perderse en silencio.
                    results.setdefault(finding_path, [])

                extra = finding.get("extra", {})
                severity_str = str(extra.get("severity", "INFO")).upper()
                risk_score = SEVERITY_SCORE.get(severity_str, 10)
                rule_id = finding.get("check_id", "semgrep-finding")
                # `check_id` es "<ruta-de-config-con-puntos>.<id-de-regla>"
                # (p. ej. "rules.semgrep.custom.bash.bash-curl-pipe-to-shell");
                # el propio `id:` de la regla, con el que está indexado
                # declared_finding_types, es siempre el último segmento.
                bare_rule_id = rule_id.split(".")[-1]
                declared_type = declared_finding_types.get(bare_rule_id)
                if declared_type == "malicious":
                    threat_nature = ThreatNature.MALICIOUS
                elif declared_type == "vulnerability":
                    threat_nature = ThreatNature.VULNERABILITY
                else:
                    # Sin finding_type declarado, o "needs_review"/
                    # "unclassified" (aún no confirmado por un humano) --
                    # cae a la heurística de respaldo.
                    threat_nature = _infer_threat_nature_from_semgrep(extra, rule_id)

                results[finding_path].append(
                    {
                        "tool": "semgrep",
                        "rule_id": rule_id,
                        "message": extra.get("message", "Hallazgo estático detectado"),
                        "line": finding.get("start", {}).get("line", 1),
                        "risk_score": risk_score,
                        "threat_nature": threat_nature,
                    }
                )
        except subprocess.TimeoutExpired:
            # WARNING, no debug -- un timeout aquí no es "esta regla no
            # aplicaba", es la capa `static` devolviendo 0 hallazgos con
            # aspecto de resultado normal (mismo código que "no se encontró
            # nada sospechoso") mientras en realidad ni siquiera terminó de
            # analizar. Verificado en vivo: sin este nivel, ese caso exacto
            # pasaba completamente desapercibido en los logs por defecto del
            # Engine API (nivel WARNING), indistinguible de un PR limpio.
            logger.warning(
                "Semgrep superó el timeout de %.0fs analizando %d ficheros de '%s' en "
                "una sola invocación agrupada -- la capa static puede estar reportando "
                "0 hallazgos para TODOS ellos sin haber terminado de analizar ninguno, "
                "no porque estén limpios.",
                _SEMGREP_SUBPROCESS_TIMEOUT_SECONDS,
                len(temp_file_paths),
                language,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Excepción al ejecutar Semgrep agrupado sobre %s: %r", temp_file_paths, exc
            )

        return results

    def _run_semgrep_on_file(
        self, temp_file_path: str, language: str, rules_dir: Path
    ) -> list[dict[str, Any]]:
        """Analiza un único fichero. `analyze()` ya NO usa este método --
        agrupa por lenguaje y llama a `_run_semgrep_on_files` directamente
        (ver esa docstring para el porqué). Se conserva como API de
        conveniencia para un solo fichero (usada por los tests unitarios de
        `_build_semgrep_config_paths`/resolución de reglas, y disponible
        para cualquier otro llamador que solo tenga un fichero)."""
        return self._run_semgrep_on_files([temp_file_path], language, rules_dir).get(
            temp_file_path, []
        )

    def _get_compiled_yara_rules(self, rules_dir: Path) -> yara.Rules | None:
        """Compila TODAS las categorías YARA publicadas (sin selección
        parcial -- requisito explícito del diseño, ver
        docs/integracion_repo_reglas.md), con caché de proceso.

        Cada fichero .yar se compila en su propio namespace (clave del
        dict `filepaths`) para evitar colisiones de nombre de regla entre
        categorías -- las reglas generadas por el repo de reglas ya
        incluyen cualquier regla "private" auxiliar que necesiten dentro
        del propio fichero, así que no hace falta compartir namespace
        entre ficheros para resolver dependencias.
        """
        yara_root = rules_dir / "rules" / "yara"
        cache_key = str(yara_root.resolve()) if yara_root.exists() else f"missing:{yara_root}"
        if cache_key in _yara_rules_cache:
            return _yara_rules_cache[cache_key]

        if not yara_root.exists():
            _yara_rules_cache[cache_key] = None
            return None

        filepaths: dict[str, str] = {}
        for index, yar_file in enumerate(sorted(yara_root.rglob("*.yar"))):
            try:
                yar_file.read_bytes()  # sanity check: legible (p. ej. no bloqueado por un AV)
            except OSError as exc:
                logger.warning("No se pudo leer la regla YARA %s, se omite: %r", yar_file, exc)
                continue
            filepaths[f"ns{index}"] = str(yar_file)

        if not filepaths:
            logger.warning("rules/yara/ existe pero no contiene ningún fichero .yar legible.")
            _yara_rules_cache[cache_key] = None
            return None

        try:
            compiled = yara.compile(filepaths=filepaths)
        except yara.Error as exc:
            logger.warning("Fallo al compilar las reglas YARA de %s: %r", yara_root, exc)
            _yara_rules_cache[cache_key] = None
            return None

        _yara_rules_cache[cache_key] = compiled
        return compiled

    def _run_yara_on_text(self, text: str, rules_dir: Path) -> list[dict[str, Any]]:
        """Ejecuta YARA sobre el mismo contenido que Semgrep (spec §4 paso
        3), con independencia del lenguaje detectado -- un webshell puede
        llevar cualquier extensión, o ninguna, así que YARA no se filtra
        por `_detect_language` como sí hace Semgrep (ver `analyze`)."""
        results: list[dict[str, Any]] = []
        compiled_rules = self._get_compiled_yara_rules(rules_dir)
        if compiled_rules is None:
            return results

        try:
            matches = compiled_rules.match(data=text.encode("utf-8", errors="replace"))
        except yara.Error as exc:
            logger.debug("Excepción al ejecutar YARA: %r", exc)
            return results

        for match in matches:
            meta = match.meta or {}
            risk_score = meta.get("risk_score", _YARA_DEFAULT_RISK_SCORE)
            if not isinstance(risk_score, int):
                risk_score = _YARA_DEFAULT_RISK_SCORE
            message = meta.get("risk_justification") or (
                f"Coincidencia con la regla YARA '{match.rule}' (posible malware/webshell)."
            )
            results.append(
                {
                    "tool": "yara",
                    "rule_id": match.rule,
                    "message": message,
                    "line": 1,  # YARA opera sobre bytes, no líneas -- ver docstring de analyze()
                    "risk_score": risk_score,
                    # Las reglas YARA aquí son SIEMPRE de detección de malware/webshells/
                    # anti-análisis (nunca de "vulnerabilidad de código legítimo"), a
                    # diferencia de Semgrep -- ver _infer_threat_nature_from_semgrep.
                    "threat_nature": ThreatNature.MALICIOUS,
                }
            )

        return results

    def _prepare_files_for_scanning(
        self, diff: NormalizedDiff, rules_dir: Path | None, temp_dir: str
    ) -> tuple[
        list[FileChange], dict[str, list[dict[str, Any]]], dict[str, list[tuple[str, FileChange]]]
    ]:
        """Fase 1 de `analyze()`: por fichero -- YARA (sin coste de
        subproceso, ver `_run_yara_on_text`) se ejecuta ya aquí; Semgrep se
        DIFIERE y se agrupa por lenguaje (para que `analyze()` pueda pagar
        el coste de compilar cada conjunto de reglas una sola vez por
        lenguaje presente en el diff, no una vez por fichero -- ver
        docstring de `_run_semgrep_on_files`, medido en vivo: 82s -> 29s con
        2 ficheros Python).

        Devuelve (ficheros elegibles en orden del diff, hallazgos YARA por
        ruta de fichero, grupos por lenguaje de `(ruta temporal, file_change)`).
        """
        ordered_files: list[FileChange] = []
        per_file_yara: dict[str, list[dict[str, Any]]] = {}
        language_groups: dict[str, list[tuple[str, FileChange]]] = {}

        for file_change in diff.files:
            if (
                file_change.status == FileStatus.DELETED
                or file_change.is_binary
                or not file_change.diff_hunk.strip()
            ):
                continue
            ordered_files.append(file_change)

            if not rules_dir:
                continue

            per_file_yara[file_change.path] = self._run_yara_on_text(
                file_change.diff_hunk, rules_dir=rules_dir
            )

            language = self._detect_language(file_change.path)
            if not language:
                continue

            ext = os.path.splitext(file_change.path)[1] or ".txt"
            temp_file = tempfile.NamedTemporaryFile(
                dir=temp_dir, suffix=ext, delete=False, mode="w", encoding="utf-8"
            )
            temp_file.write(file_change.diff_hunk)
            temp_file.close()
            language_groups.setdefault(language, []).append((temp_file.name, file_change))

        return ordered_files, per_file_yara, language_groups

    def _collect_semgrep_findings_by_file(
        self,
        language_groups: dict[str, list[tuple[str, FileChange]]],
        rules_dir: Path | None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Fase 2 de `analyze()`: una invocación de Semgrep por lenguaje
        distinto presente en el diff (no por fichero), reatribuyendo cada
        hallazgo a la ruta ORIGINAL del fichero (no la temporal) vía el
        mapeo `path_by_temp` -- ver `_run_semgrep_on_files`."""
        per_file_semgrep: dict[str, list[dict[str, Any]]] = {}
        if not rules_dir:
            return per_file_semgrep

        for language, entries in language_groups.items():
            temp_paths = [temp_path for temp_path, _fc in entries]
            path_by_temp = {temp_path: fc.path for temp_path, fc in entries}
            findings_by_temp_path = self._run_semgrep_on_files(
                temp_paths, language, rules_dir=rules_dir
            )
            for temp_path, findings in findings_by_temp_path.items():
                original_path = path_by_temp.get(temp_path)
                if original_path is None:
                    continue
                per_file_semgrep.setdefault(original_path, []).extend(findings)

        return per_file_semgrep

    def _combine_findings_with_heuristic_fallback(
        self,
        ordered_files: list[FileChange],
        per_file_semgrep: dict[str, list[dict[str, Any]]],
        per_file_yara: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """Fase 3 de `analyze()`: recombina Semgrep + YARA por fichero, en
        el mismo orden que el diff original, y aplica el escaneo heurístico
        de emergencia si ninguno de los dos produjo hallazgos para ESE
        fichero concreto (misma lógica de siempre, solo que ahora los
        hallazgos de Semgrep llegan ya calculados de la Fase 2)."""
        all_findings: list[dict[str, Any]] = []
        for file_change in ordered_files:
            semgrep_yara_findings: list[dict[str, Any]] = list(
                per_file_semgrep.get(file_change.path, [])
            ) + list(per_file_yara.get(file_change.path, []))

            for f in semgrep_yara_findings:
                f["file_path"] = file_change.path
            all_findings.extend(semgrep_yara_findings)

            # Escaneo heurístico de emergencia si Semgrep/YARA no produjo hallazgos
            if not semgrep_yara_findings:
                for label, text, line_idx in scan_diff_hunk_for_suspicious_patterns(
                    file_change.diff_hunk
                ):
                    all_findings.append(
                        {
                            "tool": "heuristic_regex",
                            "rule_id": f"static.suspicious.{label}",
                            "message": f"Patrón sospechoso detectado ({label}): {text[:80]}",
                            "line": line_idx,
                            "risk_score": 90,
                            "threat_nature": ThreatNature.MALICIOUS,
                            "file_path": file_change.path,
                        }
                    )
        return all_findings

    def analyze(self, diff: NormalizedDiff, metadata: dict[str, Any]) -> LayerResult:
        # Nota: esta capa NO escanea el diff en busca de "intentos de
        # inyección de prompt" (frases tipo "ignora las instrucciones
        # anteriores", "no marques esto") -- se probó y se revirtió (bug
        # real, reproducido: "// TODO: don't flag this edge case in the
        # linter, it's intentional", un comentario de código de lo más
        # normal, disparaba risk_score=100/MALICIOSO sin que ningún LLM
        # juzgara el contexto). Esos patrones solo son evidencia real de
        # intención de manipular al analizador cuando el propio texto imita
        # la sintaxis de una respuesta o instrucción dirigida a un LLM
        # (rol falso, JSON de respuesta falso, "responde con risk_score
        # X") -- ver `_apply_prompt_injection_floor` en `_semantic/layer.py`,
        # que sí tiene ese contexto porque compara contra lo que el propio
        # LLM concluyó, y solo dispara para el subconjunto estructural de
        # patrones, no para lenguaje genérico.
        rules_dir = self._get_rules_dir()

        # Crear directorio temporal para aislar la escritura de parches (diff_hunks)
        temp_dir = tempfile.mkdtemp(prefix="watchgate_static_")
        try:
            ordered_files, per_file_yara, language_groups = self._prepare_files_for_scanning(
                diff, rules_dir, temp_dir
            )
            per_file_semgrep = self._collect_semgrep_findings_by_file(language_groups, rules_dir)
            all_findings = self._combine_findings_with_heuristic_fallback(
                ordered_files, per_file_semgrep, per_file_yara
            )
        finally:
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir, onerror=_handle_remove_read_only)
                except Exception:  # noqa: BLE001
                    pass

        if not all_findings:
            if not rules_dir:
                return LayerResult(
                    layer_name=self.name,
                    risk_score=0,
                    justification="No se pudieron cargar las reglas de análisis estático.",
                    skipped=True,
                    skip_reason="Reglas Semgrep/YARA no disponibles",
                )
            return LayerResult(
                layer_name=self.name,
                risk_score=0,
                justification="No se encontraron hallazgos estáticos sospechosos.",
            )

        # Regla explícita de la spec §4: tomar el MÁXIMO, NUNCA SUMAR
        max_risk_score = max((f["risk_score"] for f in all_findings), default=0)
        rule_ids = list(dict.fromkeys(f["rule_id"].split(".")[-1] for f in all_findings))
        rules_str = ", ".join(rule_ids[:3])

        justification = (
            f"Se encontraron {len(all_findings)} hallazgos estáticos con puntuación "
            f"máxima de {max_risk_score} (reglas: {rules_str})."
        )

        category = RiskCategory.OFUSCACION if max_risk_score >= 50 else RiskCategory.NINGUNA
        if max_risk_score >= 70:
            confidence = Confidence.ALTA
        elif max_risk_score > 0:
            confidence = Confidence.MEDIA
        else:
            confidence = Confidence.BAJA

        structured_findings = [
            Finding(
                file_path=f.get("file_path", "desconocido"),
                line=f.get("line"),
                rule_id=f.get("rule_id", "static-finding"),
                message=f.get("message", "Hallazgo estático"),
                severity="error" if f.get("risk_score", 0) >= 50 else "warning",
                threat_nature=f.get("threat_nature", ThreatNature.VULNERABILITY),
            )
            for f in all_findings
        ]

        dominant_threat = compute_dominant_threat_nature(structured_findings)

        return LayerResult(
            layer_name=self.name,
            risk_score=max_risk_score,
            justification=justification,
            findings=structured_findings,
            category=category,
            confidence=confidence,
            threat_nature=dominant_threat,
        )
