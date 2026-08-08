"""Utilidades compartidas entre capas de análisis (spec §5, §11).

Módulo deliberadamente pequeño y sin dependencias de ninguna capa concreta:
cualquier capa (o `shortcircuit.py`) puede importar de aquí sin crear un
ciclo de imports.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

# Nombres de fichero (no rutas completas) que WatchGate reconoce como
# manifiestos de gestión de dependencias.
DEPENDENCY_MANIFEST_FILENAMES: frozenset[str] = frozenset(
    {"package.json", "requirements.txt", "Pipfile", "PKGBUILD", "Cargo.toml"}
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

    for line in diff_hunk.splitlines():
        if not line.startswith("+") or line.startswith("++"):
            continue

        script_match = _PKG_JSON_SCRIPT_REGEX.search(line)
        if script_match:
            install_scripts.append(f"{script_match.group(1)}: {script_match.group(2)}")
            continue

        dep_match = _PKG_JSON_DEP_REGEX.search(line)
        if dep_match:
            dep_name = dep_match.group(1)
            dep_version = dep_match.group(2)
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


_SUSPICIOUS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"curl\s+[^|\n]+\|\s*(sh|bash)", re.IGNORECASE), "curl_pipe_shell"),
    (re.compile(r"wget\s+[^|\n]+\|\s*(sh|bash)", re.IGNORECASE), "wget_pipe_shell"),
    (re.compile(r"eval\s*\(", re.IGNORECASE), "eval_dynamic"),
    (re.compile(r"exec\s*\(", re.IGNORECASE), "exec_dynamic"),
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
    # `.{0,30}` en vez de solo un determinante opcional: el español antepone
    # el sustantivo al adjetivo ("ignora las instrucciones anteriores"), al
    # revés que el inglés ("ignore previous instructions") -- un hueco corto
    # y libre entre "ignora"/"ignore" y "anterior"/"previous" cubre ambos
    # órdenes sin tener que enumerar la gramática de cada idioma.
    r"ignor[ae]\w*.{0,30}(previous|prior|above|anterior)",
    re.IGNORECASE,
)
_DISREGARD_RE = re.compile(r"disregard\s+(all |any |the )?(previous|prior|above)", re.IGNORECASE)
_FAKE_ROLE_MARKER_RE = re.compile(
    r"^\s*(system|assistant|user)\s*:\s*", re.IGNORECASE | re.MULTILINE
)
_INSTRUCTS_RESPONSE_RE = re.compile(
    r"respond\s+(only\s+)?with.{0,40}risk_score", re.IGNORECASE | re.DOTALL
)
_FAKE_JSON_RESPONSE_RE = re.compile(
    r'"?risk_score"?\s*[:=]\s*0\b.{0,60}(justification|confidence)',
    re.IGNORECASE | re.DOTALL,
)
_CLAIMS_PREAPPROVED_RE = re.compile(
    r"(this|el) (file|code|fichero|c[oó]digo).{0,30}"
    r"(is|has been|ya (est[aá]|fue)).{0,20}"
    r"(verified|approved|safe|verificad|aprobad|segur)",
    re.IGNORECASE,
)
_SKIP_ANALYSIS_RE = re.compile(
    r"(do not|don'?t|no)\s+(flag|report|analyze|analices|reportes|marques)\s+this",
    re.IGNORECASE,
)

_PROMPT_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
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
