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
    (re.compile(r"base64\s+(-d|--decode)", re.IGNORECASE), "base64_decode"),
    (re.compile(r"chmod\s+(\+x|777)", re.IGNORECASE), "permission_escalation"),
    (re.compile(r"nc\s+-[eE]\s+", re.IGNORECASE), "netcat_reverse_shell"),
    (re.compile(r"/dev/tcp/\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", re.IGNORECASE), "dev_tcp_shell"),
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

