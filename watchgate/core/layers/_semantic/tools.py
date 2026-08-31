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
import yara

from watchgate.core.layers._shared import parse_requirements_txt
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


def detect_new_python_dependencies(diff: NormalizedDiff) -> list[tuple[str, str]]:
    """Detecta paquetes PyPI añadidos en `requirements*.txt` dentro del diff
    (líneas `+` de un hunk), como `(nombre, "PyPI")`.
    """
    found: list[tuple[str, str]] = []
    for file_change in diff.files:
        if not _REQUIREMENTS_FILE_PATTERN.search(file_change.path):
            continue
        for dep in parse_requirements_txt(file_change.diff_hunk):
            if dep.name:
                found.append((dep.name, "PyPI"))
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


# A diferencia de `lookup_package_registry`/VT (`timeout=10.0` HTTP), este
# subprocess no tenía timeout -- el LLM puede pedir cualquier ref/path del
# propio repo analizado (no solo los tocados por el diff), así que un
# hook/lock de git atascado bloquea la llamada a la tool indefinidamente, no
# solo esos 10s. Mismo valor que el resto de tools por consistencia.
_GIT_SHOW_TIMEOUT_SECONDS = 10.0
# `capture_output=True` acumula todo el blob en memoria antes de que
# `fetch_referenced_file` pueda truncarlo -- un blob trackeado
# deliberadamente enorme (no hace falta que sea attacker-controlled desde
# fuera del repo: basta con que el LLM pida leer uno ya versionado) igual
# infla el pico de memoria del proceso, pero al menos esto acota lo que
# acaba fluyendo al prompt del LLM después.
_MAX_FETCHED_FILE_BYTES = 200_000


def _git_show_bytes(object_spec: str, repo_path: str) -> bytes | None:
    """`git show <object_spec>` local, sin red. `None` si no existe/falla."""
    try:
        result = subprocess.run(  # noqa: S603
            ["git", "show", object_spec],
            cwd=repo_path,
            capture_output=True,
            check=False,
            timeout=_GIT_SHOW_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None
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
    return raw[:_MAX_FETCHED_FILE_BYTES].decode("utf-8", errors="replace")


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


_MAX_YARA_SOURCE_CHARS = 20_000
_RULE_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{2,63}$")
_RULE_CATEGORY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


def propose_yara_rule(
    rule_name: str, category: str, yara_source: str, rationale: str
) -> dict[str, Any]:
    """Bucle de retroalimentación (A.3.1 extendido): valida y empaqueta una
    regla YARA que el LLM propone para generalizar un patrón malicioso que
    ningún hallazgo estático (Semgrep/YARA) cazó en este diff.

    Auditoría de diseño: NUNCA escribe nada a disco ni activa nada -- solo
    compila la regla de forma aislada (`yara.compile(source=...)`, nunca
    contra los ficheros reales de `rules/yara/`) para rechazar de inmediato
    sintaxis rota (el LLM ve el error y puede corregirlo en el mismo turno,
    en vez de colar basura a la cola de revisión) y devuelve un dict simple
    que `layer.py::_build_tool_executor` decide si acumular en
    `_ToolCallCounter.proposed_yara_rules`. La activación real exige
    aprobación humana explícita -- ver `PendingYaraRule`/`routers/yara_rules.py`.

    Comprobaciones, todas fail-closed (`accepted=False` con `error`
    explicativo si cualquiera falla):
    - `rule_name`/`category` con charset seguro -- se usan más tarde como
      nombre de fichero/carpeta al aprobar (`generated_yara_rules/<category>/
      <rule_name>.yar`); nunca deben poder salirse de ese directorio ni
      contener nada que no sea `[a-z0-9_]`.
    - `yara_source` compila solo, define EXACTAMENTE una regla, y su
      identificador coincide con `rule_name` (evita una regla que declara un
      nombre distinto al que luego se usaría como fichero/clave de
      deduplicación).
    - Tope de tamaño (`_MAX_YARA_SOURCE_CHARS`) -- una regla YARA legítima
      para un patrón de código nunca necesita decenas de miles de caracteres;
      esto también acota el peor caso de lo que puede acabar en la cola de
      revisión desde una sola llamada.
    """
    if not _RULE_NAME_PATTERN.match(rule_name):
        return {
            "accepted": False,
            "error": (
                "rule_name inválido -- usa minúsculas/mayúsculas/dígitos/guion bajo, "
                "empezando por letra o '_', 3-64 caracteres."
            ),
        }
    if not _RULE_CATEGORY_PATTERN.match(category):
        return {
            "accepted": False,
            "error": (
                "category inválida -- usa minúsculas/dígitos/guion bajo, empezando "
                "por letra, 2-32 caracteres (p. ej. 'webshells', 'exfiltration')."
            ),
        }
    if len(yara_source) > _MAX_YARA_SOURCE_CHARS:
        return {
            "accepted": False,
            "error": f"yara_source demasiado larga (máximo {_MAX_YARA_SOURCE_CHARS} caracteres).",
        }
    if not rationale.strip():
        return {"accepted": False, "error": "rationale no puede estar vacío."}

    try:
        compiled = yara.compile(source=yara_source)
    except yara.Error as exc:
        return {"accepted": False, "error": f"YARA no compila: {exc}"}

    identifiers = [rule.identifier for rule in compiled]
    if len(identifiers) != 1:
        return {
            "accepted": False,
            "error": (
                f"yara_source debe definir EXACTAMENTE una regla, encontradas "
                f"{len(identifiers)}: {identifiers}."
            ),
        }
    if identifiers[0] != rule_name:
        return {
            "accepted": False,
            "error": (
                f"El identificador de la regla ('{identifiers[0]}') no coincide con "
                f"rule_name ('{rule_name}')."
            ),
        }

    return {
        "accepted": True,
        "rule_name": rule_name,
        "category": category,
        "yara_source": yara_source,
        "rationale": rationale,
    }


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
    {
        "name": "propose_yara_rule",
        "description": (
            "Propón una regla YARA nueva SOLO cuando identifiques un patrón malicioso "
            "o técnica sospechosa concreta que NINGÚN hallazgo estático (Semgrep/YARA) "
            "de este análisis ya cubre, y que generaliza más allá de este PR concreto "
            "(una técnica de ofuscación, un patrón de exfiltración, la forma de un "
            "webshell...). La regla NO se activa de inmediato: queda pendiente de "
            "revisión humana antes de entrar en producción, así que puedes proponerla "
            "aunque no estés seguro al 100%, pero úsala con moderación -- nunca para "
            "hardcodear un valor literal específico de este PR (un nombre de variable, "
            "una URL exacta...), eso no generaliza a nada y sería rechazado en revisión. "
            "La regla debe compilar como YARA válido y definir EXACTAMENTE una regla "
            "cuyo identificador coincida con rule_name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "rule_name": {
                    "type": "string",
                    "description": (
                        "Identificador único en snake_case, 3-64 caracteres "
                        "(letras/dígitos/guion bajo, empieza por letra o '_')."
                    ),
                },
                "category": {
                    "type": "string",
                    "description": (
                        "Carpeta lógica en minúsculas, p. ej. 'webshells', "
                        "'exfiltration', 'obfuscation', 'backdoor'."
                    ),
                },
                "yara_source": {
                    "type": "string",
                    "description": (
                        "Cuerpo COMPLETO de la regla YARA: "
                        "'rule <rule_name> { meta: ... strings: ... condition: ... }'."
                    ),
                },
                "rationale": {
                    "type": "string",
                    "description": (
                        "Por qué este patrón merece una regla propia: qué generaliza y "
                        "qué falso positivo razonable podría tener."
                    ),
                },
            },
            "required": ["rule_name", "category", "yara_source", "rationale"],
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
