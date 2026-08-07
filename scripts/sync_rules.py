#!/usr/bin/env python3
"""Sincronización y verificación por hash de las reglas Semgrep/YARA.

Lógica reutilizable, compartida por los dos workflows consumidores del
repo privado de reglas (pablojimz/Repo-reglas-SEMGREP-y-YARA):

  - .github/workflows/sync-rules.yml     -> subcomando `sync --scope changed`
  - .github/workflows/reconcile-rules.yml -> subcomandos `fetch-manifest`,
    `check` y, si hace falta, `sync --scope full`

Se centraliza aquí (en vez de duplicar en YAML) porque la parte delicada
-- checkout disperso con Git LFS, verificación de hash POR CLAVE, y no
activar nada si una sola clave falla -- es fácil de romper por accidente
si se reescribe cada vez en `run: |` de un workflow distinto.

Diseño de seguridad clave (ver README del reto / justificación académica):
  - El `ref` de Git que se descarga es SIEMPRE el tag exacto de la versión
    (nunca `main`), así que lo que se hashea es inmutable.
  - manifest.json NO vive en el árbol git (ni en `main` ni en el propio
    tag): se publica como ASSET adjunto a la Release de GitHub (se baja
    vía `releases/download/<tag>/manifest.json`). Por eso se obtiene por
    separado, vía la Releases API, pidiendo explícitamente el release
    identificado por ese mismo tag exacto -- así la autenticidad del
    manifest sigue atada a la versión concreta que se está sincronizando,
    aunque el mecanismo de transporte ya no sea git.
  - La verificación es POR CLAVE (idioma / vendor+carpeta / categoría
    YARA) y todo-o-nada: si una sola clave falla, no se activa NINGUNA
    (ni siquiera las que sí verificaron), y se listan explícitamente las
    claves que fallaron -- nunca un booleano global.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from rules_hash import compute_dir_hash, hashes_match

# Rutas dentro del repo de reglas (ver estructura documentada por el
# usuario; ajustar aquí si el repo de reglas cambia de convención).
CUSTOM_PREFIX = "rules/semgrep/custom"
THIRD_PARTY_PREFIX = "rules/semgrep/third-party"
YARA_PREFIX = "dist/yara_scored"

# manifest.json se publica como asset adjunto a cada Release de GitHub
# (releases/download/<tag>/manifest.json), NO como fichero commiteado en
# el árbol git -- se obtiene vía la Releases API, no vía checkout/Contents API.
DEFAULT_MANIFEST_ASSET = "manifest.json"

# Rutas equivalentes DENTRO de watch_gate (este repo) donde se activa el
# contenido ya verificado. YARA se remapea de dist/yara_scored/<cat> a
# rules/yara/<cat> porque este repo organiza todo bajo rules/.
LOCAL_YARA_DIR = "rules/yara"


def _run_git(args: list[str], cwd: Path, mask: str | None = None) -> None:
    """Ejecuta un comando git, enmascarando el token en el log si aparece."""
    printable = " ".join(args)
    if mask:
        printable = printable.replace(mask, "***")
    print(f"    $ git {printable}")
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        stderr = result.stderr.replace(mask, "***") if mask else result.stderr
        raise RuntimeError(f"Fallo `git {printable}`: {stderr.strip()}")


def _checkout_rule_folders(repo: str, ref: str, token: str, dest: Path, patterns: list[str]) -> None:
    """Checkout disperso (sparse-checkout, cone mode) de las carpetas de
    reglas necesarias, fijado EXACTAMENTE al `ref` recibido, con Git LFS
    habilitado. manifest.json NO se lee de aquí -- es un asset de Release,
    se obtiene aparte vía `fetch_release_manifest` -- así que este checkout
    puede ir directo a los patrones finales, en un único paso.

    OJO con una particularidad de sparse-checkout en modo cone: al pedir
    una subcarpeta (p. ej. rules/semgrep/custom/python), Git incluye
    TAMBIÉN, sin pedirlo, los ficheros sueltos de cada carpeta ANCESTRA
    (rules/semgrep/, rules/) -- ahí vive rules/semgrep/config.yaml, que es
    config de LiteLLM sin relación con las reglas y que nunca debemos
    tocar. Por eso el checkout se hace con `--skip-smudge` (deja TODO como
    punteros de texto, nunca falla por red/permisos de un fichero que ni
    siquiera pedimos) y el contenido real solo se resuelve después, con
    `git lfs pull --include=<patterns>` acotado exactamente a las carpetas
    que sí pedimos. config.yaml se queda como puntero sin resolver, nunca
    se descarga ni se toca -- justo lo que pide la spec del proyecto.
    """
    url = f"https://x-access-token:{token}@github.com/{repo}.git"
    _run_git(
        ["clone", "--no-checkout", "--filter=blob:none", "--depth", "1", "--branch", ref, url, str(dest)],
        cwd=dest.parent,
        mask=token,
    )
    _run_git(["sparse-checkout", "init", "--cone"], cwd=dest)
    _run_git(["lfs", "install", "--local", "--skip-smudge"], cwd=dest)
    if patterns:
        _run_git(["sparse-checkout", "set", *patterns], cwd=dest)
    # Con --skip-smudge, este checkout SIEMPRE materializa como punteros de
    # texto (nunca descarga ni falla), aunque cone mode cuele algún fichero
    # "vecino" que no pedimos.
    _run_git(["checkout", ref], cwd=dest)
    # Ahora sí: resuelve el contenido real vía LFS, pero SOLO para las
    # rutas que de verdad pedimos (nunca para los "vecinos" colados por
    # cone mode, como config.yaml).
    if patterns:
        include = ",".join(f"{pattern}/**" for pattern in patterns)
        _run_git(["lfs", "pull", "--include", include], cwd=dest)


def _assert_no_lfs_pointers(directory: Path) -> None:
    """Defensa explícita frente al bug que el usuario señaló: si Git LFS no
    resolvió el contenido real, los ficheros *.yaml quedan como punteros de
    texto de ~130 bytes con esta firma. Si se detecta, se aborta con un
    mensaje claro en vez de verificar (y aceptar) un hash sobre punteros.
    """
    pointer_signature = b"version https://git-lfs.github.com/spec"
    for file_path in directory.rglob("*"):
        if not file_path.is_file():
            continue
        head = file_path.read_bytes()[:200]
        if pointer_signature in head:
            raise RuntimeError(
                f"'{file_path}' es un PUNTERO de Git LFS sin resolver, no el contenido "
                "real de la regla. La verificación de hash sobre esto sería inválida "
                "(hashearíamos el puntero, no la regla). Revisa que `lfs: true` / "
                "`git lfs pull` se hayan ejecutado correctamente."
            )


def _github_headers(token: str, accept: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get_release(repo: str, ref: str, token: str) -> dict[str, Any]:
    """Obtiene los metadatos (incluida la lista de assets) de una Release.

    `ref == "latest"` pide el último release PUBLICADO (no borrador, no
    prerelease) -- es lo que usa reconcile-rules.yml para el chequeo diario.
    Cualquier otro valor se trata como el tag exacto de la release (lo que
    usa sync-rules.yml, fijado siempre al tag recibido en el payload).
    """
    if ref == "latest":
        url = f"https://api.github.com/repos/{repo}/releases/latest"
    else:
        url = f"https://api.github.com/repos/{repo}/releases/tags/{ref}"
    response = httpx.get(url, headers=_github_headers(token, "application/vnd.github+json"), timeout=15.0)
    if response.status_code == 404:
        raise RuntimeError(
            f"No existe una Release '{ref}' en {repo} (o el token no tiene acceso a ella)."
        )
    response.raise_for_status()
    return response.json()


def _download_release_asset(repo: str, release: dict[str, Any], asset_name: str, token: str) -> bytes:
    """Descarga el CONTENIDO de un asset de Release por su nombre.

    Los assets de Release no son ficheros del árbol git: se descargan vía
    la URL de la API de cada asset (`asset["url"]`) con
    `Accept: application/octet-stream`. La URL pública
    `releases/download/<tag>/<asset>` es para navegador con sesión, no
    funciona con un token Bearer contra un repo privado.
    """
    assets = release.get("assets", [])
    match = next((a for a in assets if a.get("name") == asset_name), None)
    if match is None:
        available = ", ".join(a.get("name", "?") for a in assets) or "(ninguno)"
        raise RuntimeError(
            f"La Release '{release.get('tag_name')}' de {repo} no tiene un asset llamado "
            f"'{asset_name}'. Assets disponibles: {available}."
        )
    response = httpx.get(
        match["url"],
        headers=_github_headers(token, "application/octet-stream"),
        timeout=30.0,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.content


def fetch_release_manifest(
    repo: str, ref: str, token: str, asset_name: str
) -> tuple[str, bytes, dict[str, Any]]:
    """Descarga manifest.json como asset de Release. Devuelve
    (tag_name_real, contenido_raw, manifest_parseado)."""
    release = _get_release(repo, ref, token)
    raw = _download_release_asset(repo, release, asset_name, token)
    return release.get("tag_name", ref), raw, json.loads(raw)


def _flatten_third_party(third_party_hashes: dict[str, dict[str, str]]) -> list[tuple[str, str]]:
    return [
        (vendor, carpeta)
        for vendor, carpetas in third_party_hashes.items()
        for carpeta in carpetas
    ]


def _parse_third_party_entries(entries: list[str]) -> list[tuple[str, str]]:
    """Parsea entradas "<vendor>/<carpeta>" (formato del payload) a tuplas."""
    parsed: list[tuple[str, str]] = []
    for entry in entries:
        if "/" not in entry:
            raise ValueError(f"Entrada de third_party_changed con formato inesperado: {entry!r}")
        vendor, carpeta = entry.split("/", 1)
        parsed.append((vendor, carpeta))
    return parsed


def _resolve_scope_keys(
    manifest: dict[str, Any],
    scope: str,
    languages_changed: list[str],
    third_party_changed: list[str],
) -> tuple[list[str], list[tuple[str, str]], list[str]]:
    """Determina qué claves hay que descargar y verificar en esta ejecución.

    - languages / third_party: según el modo.
        * "changed": solo lo que vino en el payload del dispatch.
        * "full": TODO lo que el manifest declara (reconciliación completa).
    - yara: SIEMPRE todas las categorías publicadas, en ambos modos, porque
      el análisis YARA usa el catálogo completo (nunca selección parcial).
    """
    hashes = manifest.get("hashes", {})
    semgrep_hashes = hashes.get("semgrep", {})
    yara_hashes = hashes.get("yara", {})

    yara_categories = sorted(yara_hashes.keys())

    if scope == "full":
        languages = sorted(semgrep_hashes.get("custom", {}).keys())
        third_party = sorted(_flatten_third_party(semgrep_hashes.get("third_party", {})))
        return languages, third_party, yara_categories

    if scope == "changed":
        languages = sorted(set(languages_changed))
        third_party = sorted(set(_parse_third_party_entries(third_party_changed)))
        return languages, third_party, yara_categories

    raise ValueError(f"scope desconocido: {scope!r}")


def _build_sparse_patterns(
    languages: list[str], third_party: list[tuple[str, str]], yara_categories: list[str]
) -> list[str]:
    patterns = [f"{CUSTOM_PREFIX}/{lang}" for lang in languages]
    patterns += [f"{THIRD_PARTY_PREFIX}/{vendor}/{carpeta}" for vendor, carpeta in third_party]
    patterns += [f"{YARA_PREFIX}/{category}" for category in yara_categories]
    return patterns


def _verify_keys(
    dest: Path,
    manifest: dict[str, Any],
    languages: list[str],
    third_party: list[tuple[str, str]],
    yara_categories: list[str],
) -> tuple[dict[str, str], list[str]]:
    """Verifica cada clave de forma INDEPENDIENTE.

    Devuelve (hashes_verificados_por_clave, claves_fallidas). Nunca lanza
    excepción por un fallo de hash individual: recopila todos los fallos
    para poder reportarlos juntos (nunca un booleano global).
    """
    verified: dict[str, str] = {}
    failed: list[str] = []
    hashes = manifest.get("hashes", {})
    semgrep_hashes = hashes.get("semgrep", {})
    custom_hashes = semgrep_hashes.get("custom", {})
    third_party_hashes = semgrep_hashes.get("third_party", {})
    yara_hashes = hashes.get("yara", {})

    def _check(key_label: str, local_dir: Path, expected_hash: str | None) -> None:
        if expected_hash is None:
            failed.append(key_label)
            print(f"    [FALLO] {key_label}: no hay hash publicado en el manifest para esta clave.")
            return
        try:
            computed = compute_dir_hash(local_dir)
        except FileNotFoundError as exc:
            failed.append(key_label)
            print(f"    [FALLO] {key_label}: {exc}")
            return
        if hashes_match(computed, expected_hash):
            verified[key_label] = computed
            print(f"    [OK]    {key_label}: hash verificado.")
        else:
            failed.append(key_label)
            print(
                f"    [FALLO] {key_label}: Posible corrupción o manipulación de las "
                f"reglas de {key_label} — hash no coincide "
                f"(esperado={expected_hash}, obtenido={computed})."
            )

    for lang in languages:
        key = f"semgrep.custom.{lang}"
        _check(key, dest / CUSTOM_PREFIX / lang, custom_hashes.get(lang))

    for vendor, carpeta in third_party:
        key = f"semgrep.third_party.{vendor}.{carpeta}"
        expected = third_party_hashes.get(vendor, {}).get(carpeta)
        _check(key, dest / THIRD_PARTY_PREFIX / vendor / carpeta, expected)

    for category in yara_categories:
        key = f"yara.{category}"
        _check(key, dest / YARA_PREFIX / category, yara_hashes.get(category))

    return verified, failed


def _apply_verified_content(
    dest: Path,
    target_root: Path,
    manifest_raw: bytes,
    languages: list[str],
    third_party: list[tuple[str, str]],
    yara_categories: list[str],
) -> None:
    """Copia el contenido YA VERIFICADO al árbol de este repo. Solo se debe
    llamar cuando `_verify_keys` no reportó ningún fallo (todo-o-nada)."""

    def _copy_dir(src: Path, dst: Path) -> None:
        if dst.exists():
            shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)

    for lang in languages:
        _copy_dir(dest / CUSTOM_PREFIX / lang, target_root / CUSTOM_PREFIX / lang)

    for vendor, carpeta in third_party:
        _copy_dir(
            dest / THIRD_PARTY_PREFIX / vendor / carpeta,
            target_root / THIRD_PARTY_PREFIX / vendor / carpeta,
        )

    # YARA siempre se remapea de dist/yara_scored/<cat> (repo de reglas) a
    # rules/yara/<cat> (convención local de watch_gate).
    for category in yara_categories:
        _copy_dir(dest / YARA_PREFIX / category, target_root / LOCAL_YARA_DIR / category)

    # manifest.json completo, siempre (requisito explícito (d)). Se escribe
    # el contenido crudo tal cual se descargó del asset de la Release (no
    # se copia de `dest`: ya no vive en el checkout git, ver fetch_release_manifest).
    manifest_dst = target_root / "rules" / "manifest.json"
    manifest_dst.parent.mkdir(parents=True, exist_ok=True)
    manifest_dst.write_bytes(manifest_raw)


def _load_state(state_file: Path) -> dict[str, Any]:
    if not state_file.exists():
        return {"version": None, "hashes": {"semgrep": {"custom": {}, "third_party": {}}, "yara": {}}}
    return json.loads(state_file.read_text(encoding="utf-8"))


def _write_state(
    state_file: Path,
    manifest: dict[str, Any],
    verified: dict[str, str],
    triggered_by: str,
) -> None:
    """Actualiza el fichero de estado activo de forma ACUMULATIVA: cada
    sincronización solo trae un subconjunto de claves (las que cambiaron),
    así que las claves no tocadas en esta ejecución conservan el hash
    verificado en una ejecución anterior. La versión activa (puntero global)
    sí avanza siempre a la última verificada con éxito."""
    state = _load_state(state_file)
    hashes = state.setdefault("hashes", {})
    semgrep = hashes.setdefault("semgrep", {})
    semgrep.setdefault("custom", {})
    semgrep.setdefault("third_party", {})
    hashes.setdefault("yara", {})

    for key, computed_hash in verified.items():
        parts = key.split(".")
        if parts[0] == "semgrep" and parts[1] == "custom":
            state["hashes"]["semgrep"]["custom"][parts[2]] = computed_hash
        elif parts[0] == "semgrep" and parts[1] == "third_party":
            vendor, carpeta = parts[2], parts[3]
            state["hashes"]["semgrep"]["third_party"].setdefault(vendor, {})[carpeta] = computed_hash
        elif parts[0] == "yara":
            state["hashes"]["yara"][parts[1]] = computed_hash

    state["version"] = manifest.get("version")
    state["generated_at"] = manifest.get("generated_at")
    state["verified_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state["verified_by_workflow"] = triggered_by

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Copia en texto plano de la versión activa (fácil de `cat`/leer desde
    # cualquier step de cualquier workflow sin tener que parsear JSON).
    version_file = state_file.parent / ".rules-version"
    version_file.write_text(f"{state['version']}\n", encoding="utf-8")


def _write_github_output(**kwargs: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as fh:
        for key, value in kwargs.items():
            fh.write(f"{key}={value}\n")


def cmd_sync(args: argparse.Namespace) -> int:
    token = os.environ.get("RULES_REPO_TOKEN")
    if not token:
        print("ERROR: falta la variable de entorno RULES_REPO_TOKEN.", file=sys.stderr)
        return 2

    languages_changed = json.loads(args.languages_changed) if args.languages_changed else []
    third_party_changed = json.loads(args.third_party_changed) if args.third_party_changed else []

    print(f"-> Descargando manifest.json (asset de Release) de {args.rules_repo}@{args.ref}...")
    tag_name, manifest_raw, manifest = fetch_release_manifest(
        args.rules_repo, args.ref, token, args.manifest_asset
    )
    if manifest.get("version") != args.ref or tag_name != args.ref:
        # No debería poder pasar (pedimos la Release por ese tag exacto),
        # pero si el manifest o el tag_name real dijeran otra versión, es
        # una señal de inconsistencia grave en el repo de reglas -> abortar.
        print(
            f"ERROR: la Release '{tag_name}' de {args.rules_repo} tiene manifest.json con "
            f"version={manifest.get('version')!r}; no coincide con el ref solicitado {args.ref!r}.",
            file=sys.stderr,
        )
        return 1

    languages, third_party, yara_categories = _resolve_scope_keys(
        manifest, args.scope, languages_changed, third_party_changed
    )
    print(
        f"-> Claves a sincronizar: {len(languages)} lenguaje(s) custom, "
        f"{len(third_party)} carpeta(s) third-party, {len(yara_categories)} "
        "categoría(s) YARA (siempre todas)."
    )
    patterns = _build_sparse_patterns(languages, third_party, yara_categories)

    tmp_root = Path(tempfile.mkdtemp(prefix="rules-sync-"))
    dest = tmp_root / "rules-repo"
    try:
        print(f"-> Checkout disperso de {args.rules_repo}@{args.ref} (Git LFS habilitado)...")
        _checkout_rule_folders(args.rules_repo, args.ref, token, dest, patterns)
        for rel in patterns:
            _assert_no_lfs_pointers(dest / rel)

        print("-> Verificando integridad por hash, clave a clave:")
        verified, failed = _verify_keys(dest, manifest, languages, third_party, yara_categories)

        if failed:
            print(
                f"\nERROR: {len(failed)} clave(s) NO superaron la verificación de "
                f"integridad: {', '.join(failed)}."
            )
            print(
                "No se activa esta versión (ni siquiera las claves que sí "
                "verificaron): la activación es todo-o-nada por ejecución."
            )
            _write_github_output(status="failed", version=args.ref, failed_keys=",".join(failed))
            return 1

        print(f"\n-> Todas las claves verificadas ({len(verified)}). Activando versión {args.ref}...")
        target_root = Path(args.target_root)
        state_file = target_root / args.state_file
        _apply_verified_content(
            dest, target_root, manifest_raw, languages, third_party, yara_categories
        )
        _write_state(state_file, manifest, verified, args.triggered_by)

        _write_github_output(
            status="success",
            version=args.ref,
            languages_synced=str(len(languages)),
            third_party_synced=str(len(third_party)),
            yara_synced=str(len(yara_categories)),
        )
        return 0
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def cmd_fetch_manifest(args: argparse.Namespace) -> int:
    """Descarga SOLO manifest.json (sin checkout completo, sin LFS) como
    asset de la Release más reciente (o de un tag concreto), vía la
    Releases API de GitHub. Usado por reconcile-rules.yml para el chequeo
    barato diario -- manifest.json no vive en el árbol git."""
    token = os.environ.get("RULES_REPO_TOKEN")
    if not token:
        print("ERROR: falta la variable de entorno RULES_REPO_TOKEN.", file=sys.stderr)
        return 2

    print(f"-> Descargando '{args.manifest_asset}' de la Release '{args.ref}' de {args.rules_repo}...")
    tag_name, raw, _manifest = fetch_release_manifest(args.rules_repo, args.ref, token, args.manifest_asset)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(raw)
    print(f"-> Guardado en {out_path} (release real: {tag_name}).")
    _write_github_output(remote_release=tag_name)
    return 0


def _diff_hash_trees(remote: dict[str, Any], local: dict[str, Any]) -> list[str]:
    """Compara recursivamente dos árboles de hashes y devuelve la lista de
    claves (rutas con puntos) que difieren o faltan."""
    diffs: list[str] = []

    def _walk(remote_node: Any, local_node: Any, path: str) -> None:
        if isinstance(remote_node, dict):
            if not isinstance(local_node, dict):
                diffs.append(path or "<raíz>")
                return
            for key, value in remote_node.items():
                _walk(value, local_node.get(key), f"{path}.{key}" if path else key)
        else:
            if not isinstance(local_node, str) or not hashes_match(local_node, remote_node):
                diffs.append(path)

    _walk(remote.get("hashes", {}), local.get("hashes", {}), "")
    return diffs


def cmd_check(args: argparse.Namespace) -> int:
    remote_manifest = json.loads(Path(args.manifest_file).read_text(encoding="utf-8"))
    state_file = Path(args.state_file)
    local_state = _load_state(state_file)

    remote_version = remote_manifest.get("version")
    version_matches = remote_version == local_state.get("version")
    diffs = _diff_hash_trees(remote_manifest, local_state)

    if version_matches and not diffs:
        print(f"IN_SYNC: la versión activa ({local_state.get('version')}) ya coincide con la remota.")
        _write_github_output(status="in_sync", remote_version=str(remote_version))
        return 0

    print(f"OUT_OF_SYNC: activa={local_state.get('version')!r} remota={remote_version!r}")
    if diffs:
        print(f"  Claves desalineadas: {', '.join(diffs)}")
    _write_github_output(status="out_of_sync", remote_version=str(remote_version))

    if args.fail_if_out_of_sync:
        print(
            "\nERROR: tras la reconciliación, la versión activa sigue sin coincidir "
            "con la publicada. Marcando el workflow como fallido explícitamente.",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="Descarga, verifica por clave y activa reglas.")
    p_sync.add_argument("--rules-repo", required=True)
    p_sync.add_argument("--ref", required=True, help="Tag exacto a fijar (nunca 'main').")
    p_sync.add_argument("--scope", choices=["changed", "full"], required=True)
    p_sync.add_argument("--languages-changed", default="[]", help="JSON array (solo scope=changed).")
    p_sync.add_argument("--third-party-changed", default="[]", help="JSON array 'vendor/carpeta' (solo scope=changed).")
    p_sync.add_argument("--manifest-asset", default=DEFAULT_MANIFEST_ASSET, help="Nombre del asset de Release.")
    p_sync.add_argument("--target-root", required=True, help="Raíz de watch_gate donde activar el contenido.")
    p_sync.add_argument("--state-file", default="rules/.rules-state.json", help="Relativo a --target-root.")
    p_sync.add_argument("--triggered-by", default="sync_rules.py")
    p_sync.set_defaults(func=cmd_sync)

    p_fetch = sub.add_parser("fetch-manifest", help="Descarga solo manifest.json (asset de Release, sin checkout/LFS).")
    p_fetch.add_argument("--rules-repo", required=True)
    p_fetch.add_argument("--ref", default="latest", help="Tag exacto, o 'latest' para la última Release publicada.")
    p_fetch.add_argument("--manifest-asset", default=DEFAULT_MANIFEST_ASSET, help="Nombre del asset de Release.")
    p_fetch.add_argument("--out", required=True)
    p_fetch.set_defaults(func=cmd_fetch_manifest)

    p_check = sub.add_parser("check", help="Compara manifest remoto vs. estado activo local.")
    p_check.add_argument("--manifest-file", required=True)
    p_check.add_argument("--state-file", default="rules/.rules-state.json")
    p_check.add_argument("--fail-if-out-of-sync", action="store_true")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        # Queremos un mensaje de error claro y un exit code != 0 siempre,
        # nunca un fallo silencioso del workflow.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
