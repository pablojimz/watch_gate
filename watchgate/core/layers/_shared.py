"""Utilidades compartidas entre capas de análisis (spec §5, §11).

Módulo deliberadamente pequeño y sin dependencias de ninguna capa concreta:
cualquier capa (o `shortcircuit.py`) puede importar de aquí sin crear un
ciclo de imports.
"""

from __future__ import annotations

import re

# Nombres de fichero (no rutas completas) que WatchGate reconoce como
# manifiestos de gestión de dependencias.
DEPENDENCY_MANIFEST_FILENAMES: frozenset[str] = frozenset(
    {"package.json", "requirements.txt", "Pipfile", "PKGBUILD", "Cargo.toml"}
)

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

