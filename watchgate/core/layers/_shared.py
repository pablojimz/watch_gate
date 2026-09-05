"""Utilidades compartidas entre capas de análisis (spec §5, §11).

Módulo deliberadamente pequeño y sin dependencias de ninguna capa concreta:
cualquier capa (o `shortcircuit.py`) puede importar de aquí sin crear un
ciclo de imports.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from watchgate.core.models import FileChange

# Nombres de fichero (no rutas completas) que WatchGate reconoce como
# manifiestos de gestión de dependencias.
DEPENDENCY_MANIFEST_FILENAMES: frozenset[str] = frozenset(
    {
        "package.json",
        "requirements.txt",
        "Pipfile",
        "PKGBUILD",
        "Cargo.toml",
        "go.mod",
        "composer.json",
        # Lockfiles -- un `npm update`/`poetry update`/`cargo update`/
        # `go mod tidy` que solo toca el lockfile (sin tocar el manifiesto,
        # que normalmente declara un rango suelto, no la versión exacta)
        # se colaba totalmente desapercibido: 0 manifiestos tocados,
        # "nada que revisar", aunque SÍ cambió la versión exacta que se
        # instala -- justo donde se cuela una versión vulnerable sin que
        # nadie lo note. Hallazgo real (usuario), ver los parsers
        # correspondientes más abajo en este mismo fichero.
        "package-lock.json",
        "yarn.lock",
        "poetry.lock",
        "Cargo.lock",
        "go.sum",
    }
)


# --- Parseo de manifiestos de dependencias -----------------------------------
#
# Compartido entre deps_layer.py (señales de ataque a la cadena de suministro:
# typosquatting, scripts de instalación sospechosos, instalación directa por
# URL/Git) y vulnerabilities_layer.py (CVEs conocidas vía OSV) -- ambas capas
# necesitan la misma lista de "qué dependencias cambiaron en este diff", pero
# evalúan señales distintas sobre ella, y la spec (§9, A.1) exige que cada
# capa sea independiente y se ejecute en paralelo sin estado compartido entre
# ellas -- de ahí que cada una parsee el diff por su cuenta en vez de que una
# le pase el resultado a la otra.


class DependencyChange(BaseModel):
    ecosystem: str  # "npm" | "PyPI" | "aur" | "crates.io"
    name: str
    old_version: str | None = None
    new_version: str | None = None
    is_new: bool = True
    install_script: str | None = None
    is_direct_url: bool = False
    manifest_path: str = ""


_PKG_JSON_DEP_REGEX = re.compile(r'^\+\s*"([^"]+)":\s*"([^"]+)"')
_PKG_JSON_SCRIPT_REGEX = re.compile(r'^\+\s*"(preinstall|postinstall|install)":\s*"([^"]+)"')
# Campos de nivel RAÍZ (no anidados en ningún objeto) que nunca son
# dependencias -- ver también `_PKG_JSON_NON_DEP_SECTIONS` para objetos
# anidados (scripts/engines/exports/...), que necesitan seguimiento de
# sección porque sus claves internas son arbitrarias, no enumerables aquí.
_PKG_JSON_NON_DEP_KEYS = frozenset(
    {
        "name",
        "version",
        "description",
        "main",
        "module",
        "types",
        "typings",
        "browser",
        "bin",
        "files",
        "sideEffects",
        "author",
        "license",
        "private",
        "type",
        "repository",
        "bugs",
        "homepage",
        "keywords",
        "scripts",
        "packageManager",
        "engines",
        "publishConfig",
        "exports",
        "workspaces",
        "directories",
        "funding",
        "os",
        "cpu",
        "contributors",
        "maintainers",
        "config",
    }
)
# Objetos anidados cuyas claves internas NUNCA son nombres de paquete --
# bug real, reproducido en vivo contra solana-foundation/solana-web3.js
# #3872: sin esto, "compile:js"/"test:lint" (de `scripts`), "node" (de
# `engines`), "access" (de `publishConfig`), "url"/"directory" (de
# `repository` como objeto, no string), "./lib/index.cjs.js" (de
# `browser`/`exports`) se consultaban contra OSV como si fueran paquetes
# npm reales -- docenas de "paquetes" inventados por análisis, agotando el
# límite de consultas por lote (`OSV omitido: límite alcanzado`) ANTES de
# llegar a las dependencias reales del fichero, además de ensuciar la
# justificación con basura.
_PKG_JSON_NON_DEP_SECTIONS = frozenset(
    {
        "scripts",
        "engines",
        "publishConfig",
        "repository",
        "exports",
        "browser",
        "directories",
        "bin",
        "config",
        "husky",
        "lint-staged",
        "nyc",
        "jest",
        "babel",
        "eslintConfig",
        "prettier",
    }
)
_PKG_JSON_SECTION_OPEN_RE = re.compile(r'^[+\- ](\s*)"([^"]+)":\s*\{\s*$')
_PKG_JSON_SECTION_CLOSE_RE = re.compile(r"^[+\- ](\s*)\},?\s*$")


def _is_npm_url_version(version_str: str) -> bool:
    v = version_str.lower()
    return (
        v.startswith(
            (
                "git+",
                "git://",
                "http://",
                "https://",
                "file:",
                "github:",
                "bitbucket:",
                "gitlab:",
            )
        )
        or "github.com" in v
        or v.endswith((".tgz", ".tar.gz", ".git"))
    )


def parse_package_json(diff_hunk: str) -> list[DependencyChange]:
    changes: list[DependencyChange] = []
    install_scripts: list[str] = []

    # Pila (indentación, nombre_de_sección) para saber en qué objeto vive
    # cada línea -- ver `_PKG_JSON_NON_DEP_SECTIONS`. Se recorren TODAS las
    # líneas del hunk (contexto y '-' incluidos, no solo '+'), porque la
    # cabecera del objeto que abre una sección casi nunca es ella misma la
    # línea añadida -- es contexto de alrededor. Se reinicia en cada nuevo
    # bloque de hunk ('@@ ... @@'): el estado de un hunk anterior no dice
    # nada fiable sobre en qué sección empieza uno nuevo.
    section_stack: list[tuple[int, str]] = []

    for line in diff_hunk.splitlines():
        if line.startswith("@@"):
            section_stack = []
            continue
        if not line or line[0] not in "+- " or line.startswith("+++") or line.startswith("---"):
            continue

        indent_str = line[1:]
        indent = len(indent_str) - len(indent_str.lstrip(" "))

        close_match = _PKG_JSON_SECTION_CLOSE_RE.match(line)
        if close_match:
            while section_stack and section_stack[-1][0] >= indent:
                section_stack.pop()
            continue

        open_match = _PKG_JSON_SECTION_OPEN_RE.match(line)
        if open_match:
            while section_stack and section_stack[-1][0] >= indent:
                section_stack.pop()
            section_stack.append((indent, open_match.group(2)))
            continue

        if not line.startswith("+"):
            continue

        script_match = _PKG_JSON_SCRIPT_REGEX.search(line)
        if script_match:
            install_scripts.append(f"{script_match.group(1)}: {script_match.group(2)}")
            continue

        # Sección conocida como NO-dependencias (scripts/engines/...) y
        # visible en este hunk -- se descarta sin más, aunque la clave
        # interna (arbitraria: "compile:js", "node", "access"...) nunca
        # pueda enumerarse en `_PKG_JSON_NON_DEP_KEYS`. Si no hay ninguna
        # sección detectable en este hunk (`section_stack` vacía --
        # frecuente: añadir UNA dependencia en medio de una lista larga no
        # trae la cabecera "dependencies": { en el contexto visible), se
        # sigue tratando la línea como posible dependencia -- igual que
        # siempre, para no introducir falsos NEGATIVOS en el caso común.
        current_section = section_stack[-1][1] if section_stack else None
        if current_section in _PKG_JSON_NON_DEP_SECTIONS:
            continue

        dep_match = _PKG_JSON_DEP_REGEX.search(line)
        if dep_match:
            dep_name = dep_match.group(1)
            dep_version = dep_match.group(2)
            if dep_name in _PKG_JSON_NON_DEP_KEYS:
                continue
            is_direct = _is_npm_url_version(dep_version)
            changes.append(
                DependencyChange(
                    ecosystem="npm",
                    name=dep_name,
                    new_version=dep_version,
                    is_new=True,
                    is_direct_url=is_direct,
                )
            )

    if install_scripts:
        combined_script = "; ".join(install_scripts)
        if changes:
            for change in changes:
                change.install_script = combined_script
        else:
            changes.append(
                DependencyChange(
                    ecosystem="npm",
                    name="package.json (scripts)",
                    is_new=False,
                    install_script=combined_script,
                )
            )

    return changes


_REQ_EGG_REGEX = re.compile(r"#egg=([A-Za-z0-9._-]+)")
_REQ_AT_REGEX = re.compile(r"^\+\s*([A-Za-z0-9._-]+)\s*@\s*(https?://|git\+|file://|http://)")
_REQ_LINE_REGEX = re.compile(
    r"^\+\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:==|>=|<=|~=|!=|>|<)?\s*([A-Za-z0-9._-]*)?"
)


def parse_requirements_txt(diff_hunk: str) -> list[DependencyChange]:
    changes: list[DependencyChange] = []
    for line in diff_hunk.splitlines():
        if not line.startswith("+") or line.startswith("++"):
            continue
        content = line[1:].strip()
        if not content or content.startswith("#") or content.startswith("-r"):
            continue

        content = re.sub(r"^-(?:-?editable|e)\s+", "", content).strip()

        is_direct_url = False
        name: str | None = None
        version: str | None = None

        if (
            content.startswith(("git+", "http://", "https://", "file://", "svn+", "hg+"))
            or " @ " in content
        ):
            is_direct_url = True
            egg_match = _REQ_EGG_REGEX.search(content)
            at_match = _REQ_AT_REGEX.match(line)
            if egg_match:
                name = egg_match.group(1)
                version = content
            elif at_match:
                name = at_match.group(1)
                version = content
            else:
                clean_url = content.split("#")[0].rstrip("/")
                pkg_candidate = (
                    clean_url.split("/")[-1]
                    .replace(".git", "")
                    .replace(".whl", "")
                    .replace(".tar.gz", "")
                )
                name = pkg_candidate if pkg_candidate else "unknown-url-pkg"
                version = content
        else:
            match = _REQ_LINE_REGEX.match(line)
            if match:
                name = match.group(1)
                version = match.group(2) if match.group(2) else None

        if name:
            changes.append(
                DependencyChange(
                    ecosystem="PyPI",
                    name=name,
                    new_version=version,
                    is_new=True,
                    is_direct_url=is_direct_url,
                )
            )
    return changes


_PKGBUILD_DEP_REGEX = re.compile(r"^\+\s*(?:depends|makedepends)\+?=\((.*?)\)")


def parse_pkgbuild(diff_hunk: str) -> list[DependencyChange]:
    changes: list[DependencyChange] = []
    install_script_lines: list[str] = []

    for line in diff_hunk.splitlines():
        if line.startswith("+") and not line.startswith("++"):
            install_script_lines.append(line[1:])
            dep_match = _PKGBUILD_DEP_REGEX.search(line)
            if dep_match:
                deps_body = dep_match.group(1)
                deps = re.findall(r"['\"]?([a-zA-Z0-9._-]+)['\"]?", deps_body)
                for dep in deps:
                    changes.append(
                        DependencyChange(
                            ecosystem="aur",
                            name=dep,
                            is_new=True,
                        )
                    )

    combined_script = "\n".join(install_script_lines) if install_script_lines else None
    if combined_script:
        for change in changes:
            change.install_script = combined_script

    return changes


_CARGO_DEP_REGEX = re.compile(r'^\+\s*([A-Za-z0-9._-]+)\s*=\s*(?:"([^"]+)"|\{\s*(.*?)\s*\})')


def parse_cargo_toml(diff_hunk: str) -> list[DependencyChange]:
    changes: list[DependencyChange] = []
    for line in diff_hunk.splitlines():
        if not line.startswith("+") or line.startswith("++"):
            continue
        match = _CARGO_DEP_REGEX.match(line)
        if match:
            name = match.group(1)
            is_direct = False
            version: str | None = None

            if match.group(2):
                version = match.group(2)
            elif match.group(3):
                inner = match.group(3)
                v_match = re.search(r'version\s*=\s*"([^"]+)"', inner)
                if v_match:
                    version = v_match.group(1)
                else:
                    version = inner
                if "git" in inner or "path" in inner:
                    is_direct = True

            changes.append(
                DependencyChange(
                    ecosystem="crates.io",
                    name=name,
                    new_version=version,
                    is_new=True,
                    is_direct_url=is_direct,
                )
            )
    return changes


_GO_MOD_REQUIRE_SINGLE_REGEX = re.compile(
    r"^\+\s*require\s+([A-Za-z0-9._\-/]+)\s+(v\d[A-Za-z0-9._\-+]*)"
)
# La versión exige un dígito justo después de "v" (no solo `v[A-Za-z...]+`,
# que también matchea palabras normales como "ver" o "vale") -- bug real
# encontrado en revisión: sin el dígito, una línea de comentario cualquiera
# que mencione una palabra empezada en "v" ("// ver la migración a v2.0...")
# se parseaba como una dependencia Go inventada (nombre "//", versión "ver").
# Este regex genérico (sin la palabra clave "require" delante, para las
# líneas dentro de un bloque `require (...)` multilínea) es el más expuesto,
# al no tener ningún otro anclaje léxico que lo distinga de prosa normal.
_GO_MOD_REQUIRE_LINE_REGEX = re.compile(r"^\+\s*([A-Za-z0-9._\-/]+)\s+(v\d[A-Za-z0-9._\-+]*)")
_GO_MOD_REPLACE_REGEX = re.compile(
    r"^\+\s*replace\s+([A-Za-z0-9._\-/]+)(?:\s+v[^\s]+)?\s*=>\s*(.+)"
)


def parse_go_mod(diff_hunk: str) -> list[DependencyChange]:
    """Parsea adiciones de dependencias en diffs de go.mod."""
    changes: list[DependencyChange] = []
    for line in diff_hunk.splitlines():
        if not line.startswith("+") or line.startswith("++"):
            continue

        rep_match = _GO_MOD_REPLACE_REGEX.search(line)
        if rep_match:
            mod_name = rep_match.group(1)
            target = rep_match.group(2).strip()
            is_direct = target.startswith((".", "/", "../")) or "git" in target or "http" in target
            changes.append(
                DependencyChange(
                    ecosystem="Go",
                    name=mod_name,
                    new_version=target,
                    is_new=True,
                    is_direct_url=is_direct,
                )
            )
            continue

        req_single = _GO_MOD_REQUIRE_SINGLE_REGEX.search(line)
        if req_single:
            mod_name = req_single.group(1)
            version = req_single.group(2)
            changes.append(
                DependencyChange(
                    ecosystem="Go",
                    name=mod_name,
                    new_version=version,
                    is_new=True,
                    is_direct_url=False,
                )
            )
            continue

        req_line = _GO_MOD_REQUIRE_LINE_REGEX.search(line)
        if req_line:
            mod_name = req_line.group(1)
            version = req_line.group(2)
            if mod_name not in ("module", "go", "toolchain", "require", "replace", "exclude"):
                changes.append(
                    DependencyChange(
                        ecosystem="Go",
                        name=mod_name,
                        new_version=version,
                        is_new=True,
                        is_direct_url=False,
                    )
                )

    return changes


_COMPOSER_DEP_REGEX = re.compile(r'^\+\s*"([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)":\s*"([^"]+)"')
_COMPOSER_SCRIPT_REGEX = re.compile(
    r'^\+\s*"(pre-install-cmd|post-install-cmd|post-autoload-dump|post-create-project-cmd)":\s*(?:"([^"]+)"|\[(.*?)\])'
)


def parse_composer_json(diff_hunk: str) -> list[DependencyChange]:
    """Parsea adiciones de dependencias y scripts en diffs de composer.json."""
    changes: list[DependencyChange] = []
    install_scripts: list[str] = []

    for line in diff_hunk.splitlines():
        if not line.startswith("+") or line.startswith("++"):
            continue

        script_match = _COMPOSER_SCRIPT_REGEX.search(line)
        if script_match:
            cmd = script_match.group(2) or script_match.group(3) or ""
            install_scripts.append(f"{script_match.group(1)}: {cmd}")
            continue

        dep_match = _COMPOSER_DEP_REGEX.search(line)
        if dep_match:
            pkg_name = dep_match.group(1)
            pkg_version = dep_match.group(2)
            is_direct = (
                pkg_version.startswith(("git@", "http://", "https://", "file://", "dev-"))
                or "github.com" in pkg_version
                or pkg_version.endswith(".git")
            )
            changes.append(
                DependencyChange(
                    ecosystem="Packagist",
                    name=pkg_name,
                    new_version=pkg_version,
                    is_new=True,
                    is_direct_url=is_direct,
                )
            )

    if install_scripts:
        combined_script = "; ".join(install_scripts)
        if changes:
            for change in changes:
                change.install_script = combined_script
        else:
            changes.append(
                DependencyChange(
                    ecosystem="Packagist",
                    name="composer.json (scripts)",
                    is_new=False,
                    install_script=combined_script,
                )
            )

    return changes


# --- Parseo de LOCKFILES (versión exacta resuelta, no rango declarado) ------
#
# Un `npm update`/`poetry update`/`cargo update`/`go mod tidy` cambia la
# versión resuelta de una dependencia SIN tocar el manifiesto (que suele
# declarar un rango suelto tipo "^1.0.0", no la versión exacta) -- antes de
# esto, ese cambio pasaba totalmente desapercibido: 0 manifiestos tocados,
# "nada que revisar" en deps_layer.py/vulnerabilities_layer.py, aunque SÍ
# cambió de verdad la versión que se instala -- justo donde se cuela una
# versión vulnerable sin que nadie lo note (hallazgo real, reportado por el
# usuario). Estos parsers extraen (nombre, versión nueva) de las líneas
# AÑADIDAS del hunk -- no intentan reconstruir `old_version` (necesitaría
# el fichero completo, no solo el hunk): para lo que consumen estas dos
# capas (typosquatting sobre el nombre, CVEs sobre la versión resuelta),
# la versión nueva es lo único que hace falta.

_GO_SUM_LINE_REGEX = re.compile(
    r"^\+([A-Za-z0-9._\-/]+)\s+(v[0-9][A-Za-z0-9._\-+]*)(?:/go\.mod)?\s+h1:"
)


def parse_go_sum(diff_hunk: str) -> list[DependencyChange]:
    """go.sum: cada módulo aparece dos veces (hash del zip y de su go.mod) --
    se dedupe por (nombre, versión), una `DependencyChange` por par único."""
    seen: set[tuple[str, str]] = set()
    changes: list[DependencyChange] = []
    for line in diff_hunk.splitlines():
        if not line.startswith("+") or line.startswith("++"):
            continue
        match = _GO_SUM_LINE_REGEX.search(line)
        if not match:
            continue
        name, version = match.group(1), match.group(2)
        if (name, version) in seen:
            continue
        seen.add((name, version))
        changes.append(
            DependencyChange(ecosystem="Go", name=name, new_version=version, is_new=True)
        )
    return changes


_NPM_LOCK_NAME_REGEX = re.compile(r'^\+\s*"node_modules/([^"]+)":\s*\{')
_NPM_LOCK_VERSION_REGEX = re.compile(r'^\+\s*"version":\s*"([^"]+)"')


def parse_package_lock_json(diff_hunk: str) -> list[DependencyChange]:
    """package-lock.json (lockfileVersion 2/3, npm 7+): las entradas usan
    claves `"node_modules/<pkg>"` (posiblemente anidadas para paquetes
    transitivos duplicados -- se toma el último segmento tras el `node_modules/`
    final como nombre resuelto) seguidas de su `"version"` en una línea
    aparte, por eso el parseo es de dos líneas en vez de un solo regex."""
    changes: list[DependencyChange] = []
    pending_name: str | None = None
    for line in diff_hunk.splitlines():
        if not line.startswith("+") or line.startswith("++"):
            continue
        name_match = _NPM_LOCK_NAME_REGEX.search(line)
        if name_match:
            pending_name = name_match.group(1).rsplit("node_modules/", 1)[-1]
            continue
        if pending_name is not None:
            version_match = _NPM_LOCK_VERSION_REGEX.search(line)
            if version_match:
                changes.append(
                    DependencyChange(
                        ecosystem="npm",
                        name=pending_name,
                        new_version=version_match.group(1),
                        is_new=True,
                    )
                )
                pending_name = None
    return changes


_YARN_LOCK_NAME_LINE_REGEX = re.compile(r"^\+(\S.*):$")
_YARN_LOCK_VERSION_REGEX = re.compile(r'^\+\s+version\s+"([^"]+)"')


def _yarn_package_name_from_specifier(specifier: str) -> str:
    """`foo@^1.0.0` -> `foo`; `@scope/foo@^1.0.0` -> `@scope/foo` -- para un
    paquete con scope, el `@` del scope no es el separador de versión, es
    el segundo `@` de la cadena."""
    first = specifier.split(",", 1)[0].strip().strip('"')
    if first.startswith("@"):
        at_idx = first.find("@", 1)
    else:
        at_idx = first.find("@")
    return first[:at_idx] if at_idx > 0 else first


def parse_yarn_lock(diff_hunk: str) -> list[DependencyChange]:
    """yarn.lock: bloque `pkg@range, pkg@otherRange:` (línea sin indentar)
    seguido de `  version "x.y.z"` (indentada) -- mismo parseo de dos
    líneas que package-lock.json, formato de fichero distinto."""
    changes: list[DependencyChange] = []
    pending_name: str | None = None
    for line in diff_hunk.splitlines():
        if not line.startswith("+") or line.startswith("++"):
            continue
        version_match = _YARN_LOCK_VERSION_REGEX.search(line)
        if version_match and pending_name is not None:
            changes.append(
                DependencyChange(
                    ecosystem="npm",
                    name=pending_name,
                    new_version=version_match.group(1),
                    is_new=True,
                )
            )
            pending_name = None
            continue
        name_match = _YARN_LOCK_NAME_LINE_REGEX.search(line)
        if name_match and not line.startswith("+ ") and not line.startswith("+\t"):
            pending_name = _yarn_package_name_from_specifier(name_match.group(1))
    return changes


_TOML_PACKAGE_BLOCK_REGEX = re.compile(r"^\+\[\[package\]\]")
_TOML_NAME_REGEX = re.compile(r'^\+name\s*=\s*"([^"]+)"')
_TOML_VERSION_REGEX = re.compile(r'^\+version\s*=\s*"([^"]+)"')


def _parse_toml_package_blocks(diff_hunk: str, ecosystem: str) -> list[DependencyChange]:
    """poetry.lock y Cargo.lock comparten la misma estructura TOML
    (`[[package]]` con `name`/`version` como claves sueltas dentro del
    bloque) -- un único parser reutilizado por los dos, solo cambia el
    ecosistema que se le pasa. Un `[[package]]` nuevo resetea el nombre
    pendiente para no emparejar un `name` con el `version` de OTRO
    paquete si el hunk solo trae un bloque a medias."""
    changes: list[DependencyChange] = []
    pending_name: str | None = None
    for line in diff_hunk.splitlines():
        if not line.startswith("+") or line.startswith("++"):
            continue
        if _TOML_PACKAGE_BLOCK_REGEX.search(line):
            pending_name = None
            continue
        name_match = _TOML_NAME_REGEX.search(line)
        if name_match:
            pending_name = name_match.group(1)
            continue
        if pending_name is not None:
            version_match = _TOML_VERSION_REGEX.search(line)
            if version_match:
                changes.append(
                    DependencyChange(
                        ecosystem=ecosystem,
                        name=pending_name,
                        new_version=version_match.group(1),
                        is_new=True,
                    )
                )
                pending_name = None
    return changes


def parse_poetry_lock(diff_hunk: str) -> list[DependencyChange]:
    return _parse_toml_package_blocks(diff_hunk, "PyPI")


def parse_cargo_lock(diff_hunk: str) -> list[DependencyChange]:
    return _parse_toml_package_blocks(diff_hunk, "crates.io")


def parse_manifest_file_change(file_change: FileChange) -> list[DependencyChange]:
    """Parsea un cambio de fichero si es un manifiesto de dependencias
    conocido -- o su lockfile (ver bloque de parsers arriba)."""
    fname = Path(file_change.path).name
    hunk = file_change.diff_hunk
    parsed: list[DependencyChange] = []
    if fname == "package.json":
        parsed = parse_package_json(hunk)
    elif fname in ("requirements.txt", "Pipfile"):
        parsed = parse_requirements_txt(hunk)
    elif fname == "PKGBUILD":
        parsed = parse_pkgbuild(hunk)
    elif fname == "Cargo.toml":
        parsed = parse_cargo_toml(hunk)
    elif fname == "go.mod":
        parsed = parse_go_mod(hunk)
    elif fname == "composer.json":
        parsed = parse_composer_json(hunk)
    elif fname == "package-lock.json":
        parsed = parse_package_lock_json(hunk)
    elif fname == "yarn.lock":
        parsed = parse_yarn_lock(hunk)
    elif fname == "poetry.lock":
        parsed = parse_poetry_lock(hunk)
    elif fname == "Cargo.lock":
        parsed = parse_cargo_lock(hunk)
    elif fname == "go.sum":
        parsed = parse_go_sum(hunk)
    for ch in parsed:
        ch.manifest_path = file_change.path
    return parsed


_SUSPICIOUS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"curl\s+[^|\n]+\|\s*(sh|bash)", re.IGNORECASE), "curl_pipe_shell"),
    (re.compile(r"wget\s+[^|\n]+\|\s*(sh|bash)", re.IGNORECASE), "wget_pipe_shell"),
    (re.compile(r"eval\s*\(", re.IGNORECASE), "eval_dynamic"),
    # Falso positivo real, reproducido en vivo contra ccxt/ccxt: el regex
    # anterior (`exec\s*\(` sin más) pillaba `regex.exec(...)` -- el método
    # ESTÁNDAR de JavaScript para ejecutar una expresión regular
    # (`RegExp.prototype.exec`), omnipresente en cualquier código JS/TS y
    # sin relación alguna con ejecutar código dinámicamente. El
    # `(?<!\.)` excluye justo la llamada a MÉTODO (precedida de un punto)
    # sin perder el caso real que esta regla existe para cazar: los
    # payloads reales de `tests/cases/` (`malicious_eval_base64`,
    # `malreal_npm_malicious_intent_kubehook_19`...) siempre llaman a
    # `exec(...)` a secas -- el builtin de Python o `child_process.exec`
    # importado como `const { exec } = require('child_process')` y usado
    # sin punto -- nunca como `algo.exec(...)`.
    (re.compile(r"(?<!\.)\bexec\s*\(", re.IGNORECASE), "exec_dynamic"),
    (re.compile(r"base64\s+(-d|--decode)", re.IGNORECASE), "base64_decode_shell"),
    (re.compile(r"chmod\s+(\+x|777)", re.IGNORECASE), "permission_escalation"),
    (re.compile(r"nc\s+-[eE]\s+", re.IGNORECASE), "netcat_reverse_shell"),
    (re.compile(r"/dev/tcp/\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", re.IGNORECASE), "dev_tcp_shell"),
    # Equivalentes en código (no solo shell/instalación) -- añadidos tras la
    # suite de validación real (tests/cases/): varios ficheros con payload
    # confirmado usaban estos y el escaneo de shell no los veía.
    (re.compile(r"base64\.b64decode\s*\(", re.IGNORECASE), "base64_decode_python"),
    (re.compile(r"literal_eval\s*\(", re.IGNORECASE), "literal_eval_dynamic"),
    (re.compile(r"pickle\.loads?\s*\(", re.IGNORECASE), "pickle_deserialize"),
    (re.compile(r"marshal\.loads?\s*\(", re.IGNORECASE), "marshal_deserialize"),
]


def analyze_install_script_text(text: str) -> list[str]:
    """Analiza un script de instalación (preinstall/postinstall/PKGBUILD)
    buscando patrones sospechosos de ejecución remota de código u ofuscación.
    """
    findings: list[str] = []
    if not text:
        return findings

    for pattern, label in _SUSPICIOUS_PATTERNS:
        if pattern.search(text):
            findings.append(label)

    return findings


# Patrones de inyección de prompt: intentos de que el texto del propio diff
# (o de un fichero leído con fetch_referenced_file) se haga pasar por una
# instrucción para el LLM en vez de datos a analizar -- "ignora las
# instrucciones anteriores", falsos mensajes de sistema, órdenes directas
# sobre qué risk_score devolver. Semánticamente distinto de
# `_SUSPICIOUS_PATTERNS` (que busca payloads maliciosos que se EJECUTAN):
# esto busca texto que intenta MANIPULAR AL ANALIZADOR, y el mero intento ya
# es una señal de ataque en sí misma, funcione o no -- de ahí que
# `_semantic/layer.py` lo trate con un suelo propio, no como un heurístico
# de "qué mostrar", ver `find_prompt_injection_attempts`.
_IGNORE_INSTRUCTIONS_RE = re.compile(
    r"ignor[ae]\w*.{0,30}(instruction|instrucci[oó]n|prompt|directive|system).{0,30}(previous|prior|above|anterior)|"
    r"ignor[ae]\w*.{0,30}(previous|prior|above|anterior).{0,30}(instruction|instrucci[oó]n|prompt|directive|system)",
    re.IGNORECASE,
)
_DISREGARD_RE = re.compile(
    r"disregard\s+.*(instruction|prompt|system|directive)",
    re.IGNORECASE,
)
_ROLE_MARKER_LINE_RE = re.compile(
    r"^\s*(system|assistant|user)\s*:\s*\S", re.IGNORECASE | re.MULTILINE
)


class _FakeConversationDetector:
    """Detecta una conversación FALSIFICADA -- no una sola línea "system:"/
    "user:"/"assistant:" suelta.

    Causa raíz de un falso positivo real, reproducido en vivo: la versión
    anterior (una sola línea que empieza por uno de esos tres nombres +
    ":") es un patrón enormemente común FUERA de cualquier contexto de
    LLM -- una clave YAML/INI cualquiera ("user: root", "system: false"),
    una plantilla de bug report ("System: Windows 11", "User: @octocat"),
    o -- el caso real que la disparó -- un fichero de texto plano con la
    plantilla de prompt de un agente de IA, donde "system:"/"user:"/
    "assistant:" son el contenido LEGÍTIMO del propio fichero, no un
    intento de suplantar un mensaje dirigido al analizador.

    Lo que de verdad distingue un ataque real (forjar una conversación
    para que el LLM crea que ya hubo un turno previo, normalmente
    terminando en una respuesta de "assistant" ya "de acuerdo") es la
    ESTRUCTURA de intercambio: al menos DOS marcadores de rol DISTINTOS en
    el mismo texto. Una plantilla legítima de un solo campo aislado
    ("user: root" en un docker-compose.yml) nunca tiene un segundo rol
    distinto acompañándolo; una plantilla de prompt CON ejemplo de
    conversación completo, en cambio, seguirá teniendo los 2-3 roles
    juntos -- pero para ese caso ya no hace falta que este detector cargue
    solo con la decisión: `_STRUCTURAL_LLM_TARGETING_LABELS` en
    `_semantic/layer.py` solo fuerza el suelo de 100 cuando esta etiqueta
    aparece JUNTO a otra evidencia real (instrucción explícita de qué
    responder, JSON de veredicto falsificado) -- ver ese módulo."""

    def search(self, text: str) -> bool:
        roles = {m.group(1).lower() for m in _ROLE_MARKER_LINE_RE.finditer(text)}
        return len(roles) >= 2


_FAKE_ROLE_MARKER_RE = _FakeConversationDetector()
_INSTRUCTS_RESPONSE_RE = re.compile(
    r"respond\s+(only\s+)?with.{0,40}risk_score", re.IGNORECASE | re.DOTALL
)
_FAKE_JSON_RESPONSE_RE = re.compile(
    r'"?risk_score"?\s*[:=]\s*0\b.{0,60}(justification|confidence)',
    re.IGNORECASE | re.DOTALL,
)
_CLAIMS_PREAPPROVED_RE = re.compile(
    r"(this|el)\s+(file|code|fichero|c[oó]digo|pr|pull\s+request).{0,30}"
    r"(is|has\s+been|ya\s+(est[aá]|fue)).{0,20}"
    r"\b(preapproved|approved|verificad[oa]|aprobad[oa]|pre-aprobad[oa]|safe|segur[oa])\b",
    re.IGNORECASE,
)
_SKIP_ANALYSIS_RE = re.compile(
    r"(do\s+not|don'?t|no)\s+(flag|report|analyze|analices|reportes|marques)\s+this\s+(pr|pull\s+request|file|fichero|code|c[oó]digo|diff|repo|repository|security|analysis|analisis|review)",
    re.IGNORECASE,
)

# El segundo elemento de cada par expone `.search(text) -> object verdadero
# si hay coincidencia` -- normalmente un `re.Pattern[str]`, salvo
# `_FAKE_ROLE_MARKER_RE` (`_FakeConversationDetector`, ver arriba), que
# necesita mirar el texto completo en vez de una coincidencia local.
_PromptInjectionSignal = Any
_PROMPT_INJECTION_PATTERNS: list[tuple[_PromptInjectionSignal, str]] = [
    (_IGNORE_INSTRUCTIONS_RE, "ignore_previous_instructions"),
    (_DISREGARD_RE, "disregard_instructions"),
    (re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE), "role_override"),
    (_FAKE_ROLE_MARKER_RE, "fake_role_marker"),
    (_INSTRUCTS_RESPONSE_RE, "instructs_response_content"),
    (_FAKE_JSON_RESPONSE_RE, "embedded_fake_json_response"),
    (_CLAIMS_PREAPPROVED_RE, "claims_preapproved"),
    (_SKIP_ANALYSIS_RE, "instructs_to_skip_analysis"),
    (re.compile(r"\bnew\s+instructions\s*:", re.IGNORECASE), "new_instructions_marker"),
]


def find_prompt_injection_attempts(text: str) -> list[str]:
    """Etiquetas de los patrones de inyección de prompt encontrados en
    `text`. Lista vacía si no hay ninguno -- no confundir con "el fichero es
    seguro", solo significa que no se ha detectado este tipo de intento
    concreto con estos patrones (heurístico de texto, no un detector
    exhaustivo: no cubre variantes ofuscadas con Unicode/base64)."""
    if not text:
        return []
    return [label for pattern, label in _PROMPT_INJECTION_PATTERNS if pattern.search(text)]


def find_suspicious_lines(text: str) -> list[int]:
    """Índices (0-based) de las líneas de `text` que coinciden con algún
    patrón de `_SUSPICIOUS_PATTERNS`. Pensado para acotar qué extracto
    mostrar de un fichero demasiado grande para incluir entero en el
    prompt, sin tener que decidir primero si el fichero completo es
    sospechoso (`_semantic/prompting.py`, truncado de diffs grandes)."""
    if not text:
        return []
    lines = text.splitlines()
    return [
        i for i, line in enumerate(lines) if any(p.search(line) for p, _ in _SUSPICIOUS_PATTERNS)
    ]


def scan_diff_hunk_for_suspicious_patterns(diff_hunk: str) -> list[tuple[str, str, int]]:
    """Analiza líneas añadidas ('+') en un diff hunk buscando patrones de RCE/ofuscación.
    Devuelve lista de (pattern_label, matched_text, line_index).
    """
    findings: list[tuple[str, str, int]] = []
    if not diff_hunk:
        return findings

    line_idx = 1
    for line in diff_hunk.splitlines():
        if line.startswith("+") and not line.startswith("++"):
            added_text = line[1:]
            for pattern, label in _SUSPICIOUS_PATTERNS:
                if pattern.search(added_text):
                    findings.append((label, added_text.strip(), line_idx))
        line_idx += 1
    return findings
