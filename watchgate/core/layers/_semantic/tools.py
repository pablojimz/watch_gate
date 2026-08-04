"""Herramientas acotadas de la capa semántica (A.3.1, §7.2)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable
from typing import Any

import httpx

from watchgate.core.models import NormalizedDiff

_OSV_API_URL = "https://api.osv.dev/v1/query"
_VT_FILE_REPORT_URL = "https://www.virustotal.com/api/v3/files/{file_hash}"

FORCE_FINAL_ANSWER_MESSAGE = (
    "Ya has usado el máximo de herramientas permitidas. Responde ahora con el JSON final."
)


class ToolCallBudget:
    """Límite duro de llamadas a herramientas, compartido por referencia a lo
    largo de una misma conversación con el LLM."""

    def __init__(self, max_calls: int = 3) -> None:
        self.max_calls = max_calls
        self.calls_made = 0

    @property
    def exhausted(self) -> bool:
        return self.calls_made >= self.max_calls

    def record_call(self) -> None:
        self.calls_made += 1


def lookup_package_registry(
    name: str, ecosystem: str, version: str | None = None
) -> dict[str, Any]:
    """Consulta el registro de vulnerabilidades OSV para un paquete.

    Misma llamada que necesita deps_layer.py (§5); hasta que esa capa exista,
    esta función la hace de forma autónoma en vez de bloquearse en ella.
    """
    body: dict[str, Any] = {"package": {"name": name, "ecosystem": ecosystem}}
    if version:
        body["version"] = version
    try:
        response = httpx.post(_OSV_API_URL, json=body, timeout=10.0)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        # httpx.HTTPError: fallos de red/timeout/status >= 400.
        # json.JSONDecodeError: un 200 con cuerpo no-JSON (proxy, mantenimiento...).
        # Ninguno de los dos debe subir el score por la mera indisponibilidad
        # del servicio (mismo criterio que exige la spec para deps_layer §5).
        return {"error": repr(exc), "vulns": []}


_REQUIREMENTS_FILE_PATTERN = re.compile(r"(^|/)requirements[\w.-]*\.txt$")
_REQUIREMENTS_LINE_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def detect_new_python_dependencies(diff: NormalizedDiff) -> list[tuple[str, str]]:
    """Detecta paquetes PyPI añadidos en `requirements*.txt` dentro del diff
    (líneas `+` de un hunk), como `(nombre, "PyPI")`.

    Heurística deliberadamente estrecha: un único formato de manifest, sin
    resolver extras/marcadores de entorno. Parsear manifests de verdad
    (`pyproject.toml`, `Pipfile`, `package.json`...) es tarea de
    `deps_layer.py` (Línea 3, §5); esto es un stand-in autónomo para la capa
    semántica, mismo criterio que `lookup_package_registry` de arriba.
    """
    found: list[tuple[str, str]] = []
    for file_change in diff.files:
        if not _REQUIREMENTS_FILE_PATTERN.search(file_change.path):
            continue
        for line in file_change.diff_hunk.splitlines():
            if not line.startswith("+") or line.startswith("++"):
                continue
            content = line[1:].strip()
            if not content or content.startswith("#"):
                continue
            match = _REQUIREMENTS_LINE_PATTERN.match(content)
            if match:
                found.append((match.group(1), "PyPI"))
    return found


_MAX_DEPENDENCY_CHECKS = 10


def gather_dependency_findings(diff: NormalizedDiff) -> list[dict[str, Any]]:
    """Para cada dependencia nueva detectada en el diff, consulta OSV en vivo
    (mismo mecanismo que `lookup_package_registry`, pero como paso previo
    automático, no como tool que el LLM tiene que decidir pedir) y devuelve
    solo los hallazgos con vulnerabilidades reales -- un paquete limpio no
    aporta nada al prompt y solo añadiría ruido.

    Tope duro de `_MAX_DEPENDENCY_CHECKS` consultas: a diferencia de
    `lookup_package_registry` como tool (acotada por `ToolCallBudget`), esto
    se ejecuta automáticamente en cada análisis sin caché ni presupuesto de
    por medio -- un `requirements.txt` con muchas líneas nuevas (p. ej. un
    `pip freeze` inicial) no debe traducirse en decenas de llamadas HTTP
    secuenciales bloqueando el análisis.
    """
    findings = []
    for name, ecosystem in detect_new_python_dependencies(diff)[:_MAX_DEPENDENCY_CHECKS]:
        result = lookup_package_registry(name, ecosystem)
        vulns = result.get("vulns") or []
        if not vulns:
            continue
        vuln_ids = [str(v.get("id", "?")) for v in vulns[:3]]
        findings.append(
            {"name": name, "ecosystem": ecosystem, "vulns_summary": "; ".join(vuln_ids)}
        )
    return findings


def make_get_commit_history_tool(
    fetch_commit_history: Callable[[str, str], dict[str, Any]],
) -> Callable[[str, str], dict[str, Any]]:
    """Construye la tool `get_commit_history`, inyectando el callback real
    del adaptador de plataforma (p. ej. GitHubClient), tal y como exige la
    spec ("vía adaptador, inyectado como callback")."""

    def get_commit_history(author_login: str, repo: str) -> dict[str, Any]:
        return fetch_commit_history(author_login, repo)

    return get_commit_history


def _resolve_git_object_spec(ref: str, path: str) -> str | None:
    """Valida `ref:path` antes de invocar git; `None` si se rechaza.

    `ref` y `path` los propone el LLM: un valor que empiece por "-" se
    interpretaría como una opción de `git show` en vez de como parte de la
    revisión/ruta (inyección de argumentos clásica al envolver un CLI). No se
    puede usar el separador `--` como mitigación aquí porque cambia el
    significado de la sintaxis `rev:path` (pasa a tratarse como pathspec, no
    como el blob de esa ruta en esa revisión) — se valida el prefijo en su
    lugar.
    """
    object_spec = f"{ref}:{path}"
    if object_spec.startswith("-"):
        return None
    return object_spec


def _git_show_bytes(object_spec: str, repo_path: str) -> bytes | None:
    """`git show <object_spec>` local, sin red. `None` si no existe."""
    result = subprocess.run(  # noqa: S603
        ["git", "show", object_spec],
        cwd=repo_path,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def fetch_referenced_file(path: str, ref: str, repo_path: str) -> str:
    object_spec = _resolve_git_object_spec(ref, path)
    if object_spec is None:
        return ""
    raw = _git_show_bytes(object_spec, repo_path)
    if raw is None:
        return ""
    return raw.decode("utf-8", errors="replace")


def check_file_reputation(path: str, ref: str, repo_path: str) -> dict[str, Any]:
    """Reputación en VirusTotal del contenido real de un fichero en una
    revisión dada: se calcula su SHA256 (mismo mecanismo de resolución que
    `fetch_referenced_file`, con la misma protección contra inyección de
    argumentos) y se consulta contra la API de ficheros de VT. Pensada para
    el caso XZ Utils: blobs/binarios ya conocidos como maliciosos colándose
    en un PR dentro de un fichero de test o similar, invisibles al leer el
    diff como texto.

    Opcional de verdad: si no hay `WATCHGATE_VT_API_KEY` configurada, no se
    intenta ninguna llamada (VT exige cuenta, y el tier gratuito tiene un
    límite de peticiones muy bajo). `build_tool_schemas()` ni siquiera ofrece
    esta tool al LLM en ese caso, así que en la práctica solo se ejecuta si
    alguien la llama directamente sin esa variable — de ahí este mismo aviso
    aquí también, por si acaso.
    """
    api_key = os.environ.get("WATCHGATE_VT_API_KEY")
    if not api_key:
        return {"error": "VirusTotal no configurado (WATCHGATE_VT_API_KEY ausente)"}

    object_spec = _resolve_git_object_spec(ref, path)
    if object_spec is None:
        return {"error": "ref/path inválidos"}
    raw = _git_show_bytes(object_spec, repo_path)
    if raw is None:
        return {"error": "fichero no encontrado en esa revisión"}

    file_hash = hashlib.sha256(raw).hexdigest()
    try:
        response = httpx.get(
            _VT_FILE_REPORT_URL.format(file_hash=file_hash),
            headers={"x-apikey": api_key},
            timeout=10.0,
        )
        if response.status_code == 404:
            return {"sha256": file_hash, "known_to_virustotal": False}
        response.raise_for_status()
        attributes = response.json().get("data", {}).get("attributes", {})
        stats = attributes.get("last_analysis_stats", {})
        return {
            "sha256": file_hash,
            "known_to_virustotal": True,
            "malicious": stats.get("malicious", 0),
            "suspicious": stats.get("suspicious", 0),
            "total_engines": sum(stats.values()) if stats else 0,
            "meaningful_name": attributes.get("meaningful_name"),
        }
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        # Mismo criterio que lookup_package_registry: una indisponibilidad
        # del servicio no debe subir el score por sí sola.
        return {"sha256": file_hash, "error": repr(exc)}


_BASE_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "lookup_package_registry",
        "description": (
            "Consulta si un paquete/versión de un ecosistema (npm, PyPI, AUR...) tiene "
            "vulnerabilidades conocidas registradas en OSV."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nombre del paquete."},
                "ecosystem": {
                    "type": "string",
                    "description": "Ecosistema del paquete (p. ej. 'npm', 'PyPI').",
                },
                "version": {
                    "type": "string",
                    "description": "Versión concreta a consultar (opcional).",
                },
            },
            "required": ["name", "ecosystem"],
        },
    },
    {
        "name": "get_commit_history",
        "description": (
            "Devuelve el historial de contribuciones de un login de autor a un "
            "repositorio concreto, tal y como lo ve la plataforma (GitHub/GitLab)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "author_login": {"type": "string", "description": "Login del autor."},
                "repo": {"type": "string", "description": "Repositorio en formato owner/repo."},
            },
            "required": ["author_login", "repo"],
        },
    },
    {
        "name": "fetch_referenced_file",
        "description": (
            "Lee el contenido completo de un fichero del repositorio en un commit "
            "concreto (git show), para inspeccionar contexto no incluido en el diff."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta del fichero dentro del repo."},
                "ref": {"type": "string", "description": "SHA de commit o referencia git."},
                # repo_path NO se le pide al modelo: el executor siempre usa el
                # repo_path real del diff que se está analizando, nunca uno propuesto
                # por el LLM (evita que el modelo pueda apuntar a otra ruta del disco).
            },
            "required": ["path", "ref"],
        },
    },
]

_VT_TOOL_SCHEMA: dict[str, Any] = {
    "name": "check_file_reputation",
    "description": (
        "Consulta en VirusTotal la reputación de un fichero por su contenido real "
        "(hash) en una revisión concreta del repositorio, para detectar blobs o "
        "binarios ya conocidos como maliciosos que se cuelan en el PR. Úsala solo "
        "cuando el diff introduce o modifica un fichero binario u ofuscado que no "
        "se pueda evaluar leyendo su texto (p. ej. un fichero de test binario)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Ruta del fichero dentro del repo."},
            "ref": {"type": "string", "description": "SHA de commit o referencia git."},
        },
        "required": ["path", "ref"],
    },
}


def build_tool_schemas() -> list[dict[str, Any]]:
    """Esquemas de las tools que se ofrecen al LLM.

    `check_file_reputation` solo se incluye si hay `WATCHGATE_VT_API_KEY`
    configurada: sin cuenta de VirusTotal no tiene sentido ofrecérsela al
    modelo (fallaría siempre, y el tier gratuito de VT tiene un límite de
    peticiones demasiado bajo para depender de él por defecto).
    """
    schemas = list(_BASE_TOOL_SCHEMAS)
    if os.environ.get("WATCHGATE_VT_API_KEY"):
        schemas.append(_VT_TOOL_SCHEMA)
    return schemas
