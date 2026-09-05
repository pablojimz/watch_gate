"""Ingesta de avisos de seguridad reales en el corpus del RAG.

Conecta con la API pública de GitHub Security Advisories
(https://api.github.com/advisories) y convierte cada aviso en un documento
`.md` del corpus (`core/rag/corpus/advisory_*.md`), con el mismo formato que
los casos curados a mano (H1 con prefijo de tipo + secciones H2), para que
tanto el indexado vectorial (`watchgate rag reindex`) como la vista del
corpus del dashboard (`routers/rag.py`) los traten exactamente igual.

La fuente por defecto es `type=malware`: el catálogo de PAQUETES MALICIOSOS
conocidos (npm, PyPI, ...) que GitHub importa de OpenSSF -- exactamente el
conocimiento de cadena de suministro que un LLM generalista no tiene fresco
y que WatchGate necesita para reconocer una dependencia envenenada en un
diff. `type=reviewed` (CVEs curados por GitHub) también está disponible.

Sin autenticación obligatoria: la API funciona anónima (60 peticiones/hora,
de sobra para un sync). Si hay `GITHUB_TOKEN`/`WATCHGATE_GITHUB_TOKEN` en el
entorno se usa (5000/hora). No se importa nada de `watchgate.adapters` a
propósito -- este módulo vive en `core` y el contrato de import-linter
prohíbe esa dirección; httpx directo, igual que `_semantic/tools.py`.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_ADVISORIES_API_URL = "https://api.github.com/advisories"
_REQUEST_TIMEOUT_SECONDS = 15.0
_PAGE_SIZE_MAX = 100

# Prefijo de fichero: distingue a simple vista (y en git) los documentos
# sincronizados automáticamente de los casos curados a mano, y hace
# idempotente el sync (mismo aviso -> mismo fichero, se sobrescribe).
ADVISORY_FILE_PREFIX = "advisory_"

# Ecosistemas por defecto: los dos donde WatchGate detecta dependencias
# nuevas hoy (requirements*.txt / package.json) y donde se concentran las
# campañas de paquetes maliciosos documentadas en el corpus curado.
DEFAULT_ECOSYSTEMS: tuple[str, ...] = ("npm", "pip")
DEFAULT_ADVISORY_TYPE = "malware"
DEFAULT_LIMIT_PER_ECOSYSTEM = 30

# Truncado del cuerpo del aviso: algunos avisos `reviewed` traen
# descripciones larguísimas; el chunking del indexer (1000 chars/fragmento)
# hace el resto, esto solo evita ficheros desproporcionados.
_MAX_DESCRIPTION_CHARS = 4000

_NON_SAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9_-]+")

# Los avisos importados de OpenSSF empiezan con una línea
# '## Source: ossf-package-analysis (<sha256>)' y terminan con un pie
# '---\nCredit: ...' -- ver _clean_description.
_SOURCE_HEADING = re.compile(r"^#{1,6}\s*Source:.*$", re.MULTILINE)
_EMBEDDED_HEADING_MARKS = re.compile(r"^#{1,6}\s+", re.MULTILINE)


def _clean_description(description: str) -> str:
    """Adecenta el cuerpo del aviso tal y como llega de la API:

    - fuera la línea '## Source: ossf-package-analysis (<sha256>)': un hash
      de 64 hex no aporta nada al embedding, y al ser un H2 embebido rompía
      el resumen que muestra el dashboard (toma el primer párrafo tras el
      primer H2 del documento);
    - fuera el pie 'Credit: ...' y sus separadores '---' (el enlace a la
      fuente ya va en la sección '## Datos del aviso');
    - cualquier otro encabezado markdown embebido se degrada a texto plano
      para no competir con la estructura H1/H2 propia del documento.
    """
    text = _SOURCE_HEADING.sub("", description)
    kept_lines = [
        line
        for line in text.splitlines()
        if line.strip() != "---" and not line.strip().lower().startswith("credit:")
    ]
    text = _EMBEDDED_HEADING_MARKS.sub("", "\n".join(kept_lines))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _affected_package_names(advisory: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for vuln in advisory.get("vulnerabilities") or []:
        if not isinstance(vuln, dict):
            continue
        name = (vuln.get("package") or {}).get("name")
        if name and name not in names:
            names.append(name)
    return names


def _github_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("WATCHGATE_GITHUB_TOKEN")


def _request_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = _github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_advisories(
    advisory_type: str = DEFAULT_ADVISORY_TYPE,
    ecosystem: str | None = None,
    limit: int = DEFAULT_LIMIT_PER_ECOSYSTEM,
) -> list[dict[str, Any]]:
    """Descarga hasta `limit` avisos de la API de GitHub, paginando.

    Un fallo de red/HTTP devuelve lo acumulado hasta ese momento (con
    warning) en vez de lanzar: el sync es un enriquecimiento best-effort
    del corpus, no debe romper el comando entero porque una página falle.
    """
    collected: list[dict[str, Any]] = []
    page = 1
    while len(collected) < limit:
        params: dict[str, str | int] = {
            "type": advisory_type,
            "per_page": min(_PAGE_SIZE_MAX, limit - len(collected)),
            "page": page,
        }
        if ecosystem:
            params["ecosystem"] = ecosystem
        try:
            response = httpx.get(
                _ADVISORIES_API_URL,
                params=params,
                headers=_request_headers(),
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            batch = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "Fallo descargando avisos (type=%s, ecosystem=%s, page=%d): %r. "
                "Se continúa con los %d ya descargados.",
                advisory_type,
                ecosystem,
                page,
                exc,
                len(collected),
            )
            break
        if not isinstance(batch, list) or not batch:
            break
        collected.extend(a for a in batch if isinstance(a, dict))
        if len(batch) < int(params["per_page"]):
            break  # última página
        page += 1
    return collected[:limit]


def advisory_case_id(ghsa_id: str) -> str:
    """Nombre de fichero (sin `.md`) para un aviso. Compatible con el patrón
    `_SAFE_CASE_ID` del router del dashboard (`^[A-Za-z0-9_-]+$`)."""
    return ADVISORY_FILE_PREFIX + _NON_SAFE_ID_CHARS.sub("-", ghsa_id.strip().lower())


def _affected_packages_lines(advisory: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for vuln in advisory.get("vulnerabilities") or []:
        if not isinstance(vuln, dict):
            continue
        package = vuln.get("package") or {}
        name = package.get("name")
        if not name:
            continue
        ecosystem = package.get("ecosystem", "?")
        version_range = vuln.get("vulnerable_version_range") or "todas las versiones"
        patched = vuln.get("first_patched_version")
        patched_note = f"; corregido en {patched}" if patched else ""
        lines.append(
            f"- `{name}` ({ecosystem}), versiones afectadas: {version_range}{patched_note}"
        )
    return lines


def advisory_to_markdown(advisory: dict[str, Any]) -> str | None:
    """Convierte un aviso de la API en un documento del corpus.

    `None` si al aviso le faltan los campos mínimos (id o resumen) --
    mejor saltarlo que indexar un documento vacío.
    """
    ghsa_id = advisory.get("ghsa_id")
    summary = (advisory.get("summary") or "").strip()
    if not ghsa_id or not summary:
        return None

    advisory_type = advisory.get("type") or "unknown"
    description = _clean_description(advisory.get("description") or "")
    if len(description) > _MAX_DESCRIPTION_CHARS:
        description = description[:_MAX_DESCRIPTION_CHARS].rstrip() + " […]"
    if not description:
        description = summary

    package_lines = _affected_packages_lines(advisory)
    package_names = _affected_package_names(advisory)
    # Nombres reales en el patrón, no un genérico "los paquetes de arriba":
    # el texto de plantilla compartido por todos los avisos es casi idéntico
    # entre sí en el espacio de embeddings -- meter el nombre del paquete en
    # cada sección hace cada documento distintivo, y el nombre es justo lo
    # que aparecerá en el diff (la consulta del retriever) cuando alguien
    # añada esa dependencia.
    names_clause = (
        ", ".join(f"`{name}`" for name in package_names[:5]) or "los paquetes listados arriba"
    )

    detail_lines = [f"- Tipo de aviso: {advisory_type}"]
    if advisory.get("severity"):
        detail_lines.append(f"- Severidad: {advisory['severity']}")
    if advisory.get("cve_id"):
        detail_lines.append(f"- CVE: {advisory['cve_id']}")
    if advisory.get("published_at"):
        detail_lines.append(f"- Publicado: {advisory['published_at']}")
    if advisory.get("html_url"):
        detail_lines.append(f"- Fuente: {advisory['html_url']}")

    if advisory_type == "malware":
        pattern = (
            f"Diff que añade (o fija por primera vez) una dependencia sobre "
            f"{names_clause}, en cualquier versión del rango afectado -- el "
            "paquete en sí ES el malware, no hace falta ningún otro cambio "
            "sospechoso en el diff para que el riesgo sea máximo."
        )
    else:
        pattern = (
            f"Diff que añade o mantiene una dependencia sobre {names_clause} "
            "dentro del rango de versiones afectado, sin actualizar a la "
            "versión corregida."
        )

    sections = [
        f"# Aviso: {summary} ({ghsa_id})",
        "",
        "## Resumen",
        "",
        description,
        "",
    ]
    if package_lines:
        sections += ["## Paquetes afectados", "", *package_lines, ""]
    sections += [
        "## Datos del aviso",
        "",
        *detail_lines,
        "",
        "## Patrón a vigilar",
        "",
        pattern,
        "",
    ]
    return "\n".join(sections)


def sync_advisories_to_corpus(
    corpus_dir: Path,
    ecosystems: tuple[str, ...] = DEFAULT_ECOSYSTEMS,
    advisory_type: str = DEFAULT_ADVISORY_TYPE,
    limit_per_ecosystem: int = DEFAULT_LIMIT_PER_ECOSYSTEM,
) -> list[Path]:
    """Descarga avisos y los escribe como `.md` del corpus. Devuelve las
    rutas escritas (nuevas o actualizadas). Idempotente: el mismo aviso
    siempre acaba en el mismo fichero, y un contenido idéntico no se
    reescribe (para no ensuciar mtimes/git sin cambios reales)."""
    corpus_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    seen_ids: set[str] = set()
    for ecosystem in ecosystems:
        for advisory in fetch_advisories(
            advisory_type=advisory_type, ecosystem=ecosystem, limit=limit_per_ecosystem
        ):
            markdown = advisory_to_markdown(advisory)
            if markdown is None:
                continue
            case_id = advisory_case_id(str(advisory["ghsa_id"]))
            if case_id in seen_ids:
                continue  # un aviso puede listar paquetes de varios ecosistemas
            seen_ids.add(case_id)
            path = corpus_dir / f"{case_id}.md"
            if path.exists() and path.read_text(encoding="utf-8") == markdown:
                continue
            _write_atomic(path, markdown)
            written.append(path)
    return written


def _write_atomic(path: Path, content: str) -> None:
    """Escribe vía fichero temporal + `os.replace` en vez de
    `path.write_text` directo -- defensa en profundidad frente a dos
    ejecuciones de `sync_advisories_to_corpus` solapadas (el guardado
    principal contra eso es deduplicar el `job_id` de la tarea que llama a
    esto, ver `dashboard/backend/main.py::_enqueue_rag_sync_deduped`; esto
    cubre cualquier otra vía de invocación concurrente, presente o
    futura). Cada llamada escribe a su PROPIO fichero temporal (nombre con
    PID -- dos ejecuciones nunca comparten uno), así que nunca hay dos
    procesos con un descriptor abierto sobre el MISMO `path` a la vez;
    `os.replace` es atómico incluso si otro proceso reemplaza `path` justo
    antes: el resultado final es el contenido de quien reemplace último,
    nunca un fichero truncado/a medio escribir ni un
    `PermissionError` por colisión de escrituras simultáneas (reproducido
    en vivo: 163 casos en una noche con `path.write_text` directo)."""
    # PID + hilo + aleatorio: el PID solo no basta -- reproducido en vivo,
    # dos ejecuciones concurrentes en el MISMO proceso (dos hilos, no dos
    # jobs de RQ) comparten PID y podían pisarse el propio temporal antes
    # de que `os.replace` corriera (`FileNotFoundError` en vez del
    # `PermissionError` original, mismo síntoma de fondo: dos escritores a
    # la vez). El caso real de este bug es entre PROCESOS (jobs de RQ en
    # work-horses separados, PID distinto), pero un sufijo único de verdad
    # no depende de esa suposición.
    suffix = f"{os.getpid()}-{threading.get_ident()}-{uuid.uuid4().hex[:8]}"
    tmp_path = path.with_name(f"{path.name}.{suffix}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)
