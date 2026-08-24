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
    description = (advisory.get("description") or "").strip()
    if len(description) > _MAX_DESCRIPTION_CHARS:
        description = description[:_MAX_DESCRIPTION_CHARS].rstrip() + " […]"
    if not description:
        description = summary

    package_lines = _affected_packages_lines(advisory)

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
            "Diff que añade (o fija por primera vez) una dependencia sobre "
            "cualquiera de los paquetes listados arriba, en cualquier versión "
            "del rango afectado -- el paquete en sí ES el malware, no hace "
            "falta ningún otro cambio sospechoso en el diff para que el "
            "riesgo sea máximo."
        )
    else:
        pattern = (
            "Diff que añade o mantiene una dependencia sobre los paquetes "
            "listados arriba dentro del rango de versiones afectado, sin "
            "actualizar a la versión corregida."
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
            path.write_text(markdown, encoding="utf-8")
            written.append(path)
    return written
