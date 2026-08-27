"""Construcción del mapa de conocimiento de un repo (ficheros, resumen,
grafo de imports) -- alimenta `RepoGraphNode`/`RepoGraphEdge`/
`RepoArchitectureSummary` (`watchgate/db/models.py`) desde
`watchgate/dashboard/backend/tasks.py::build_repo_knowledge_graph`.

Deliberadamente separado de `core/layers/_semantic/chunking.py`: esas
funciones (`build_reference_graph`, etc.) trabajan sobre `FileChange` con
un `diff_hunk` y reconstruyen el contenido "nuevo" a partir del parche --
aquí ya tenemos el contenido REAL completo de cada fichero (del árbol de
GitHub, o de un snapshot subido de un servidor Git propio), así que no
hace falta reconstruir nada; se reutiliza directamente
`ast_boundaries.import_specifiers` con el mismo criterio de correlación
por "stem" del nombre de fichero que usa `chunking.build_reference_graph`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlmodel import Session, delete, select

from watchgate.core.diffparser import _infer_language
from watchgate.core.layers._semantic import ast_boundaries
from watchgate.core.layers._semantic.client import LLMClient
from watchgate.core.layers._semantic.llm_factory import build_llm_client
from watchgate.core.rag.indexer import DEFAULT_INDEX_PATH, get_chroma_client
from watchgate.core.rag.retriever import _get_embedding_model
from watchgate.db.connection import get_session
from watchgate.db.models import RepoArchitectureSummary, RepoGraphEdge, RepoGraphNode

logger = logging.getLogger("watchgate.repo_graph")

# Llamadas de resumen por fichero independientes entre sí, sin paso de
# reduce compartido (a diferencia del map-reduce de diffs de `layer.py`,
# `_CHUNK_WORKERS=6`) -- se puede paralelizar mucho para que un repo de
# cientos de ficheros termine en minutos, no horas, contra un proveedor
# cloud (Anthropic/Gemini) con concurrencia real.
_SUMMARY_WORKERS = 20

# Un servidor Ollama local sirve las peticiones prácticamente en serie (un
# único slot de GPU/modelo) -- lanzar 20 a la vez contra él no las hace ir
# más rápido, solo las pone en cola hasta que superan el timeout y varias
# degradan a "unknown" (reproducido: con 6-8 en paralelo, varios daban
# ReadTimeout). Inicialmente esto se bajó a 1 (totalmente en serie), pero
# contra un repo de verdad de 232 ficheros eso significa horas -- lento a
# propósito no es la respuesta correcta. En su lugar: concurrencia
# moderada aquí + un reintento en serie después (ver `_run_indexing`) solo
# para los que degradaron, que es donde la fiabilidad de verdad hace
# falta -- la mayoría termina rápido en paralelo, y los pocos que fallan
# por la cola se recuperan solos sin pagar el coste serie del repo entero.
_SUMMARY_WORKERS_LOCAL = 4

# Excluidos del mapa de conocimiento -- ni aportan arquitectura ni merecen
# gastar una llamada de LLM por fichero: dependencias vendorizadas,
# artefactos de build, y binarios que ni siquiera se pueden decodificar
# como texto (ya filtrados aparte por `get_file_content` devolviendo None).
_EXCLUDED_DIR_SEGMENTS = frozenset(
    {
        "node_modules",
        "vendor",
        "dist",
        "build",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "target",
        ".next",
        ".pytest_cache",
    }
)
_EXCLUDED_FILENAME_SUFFIXES = (
    ".lock",
    ".min.js",
    ".min.css",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".zip",
    ".tar",
    ".gz",
    ".pdf",
    ".mp4",
    ".mp3",
)
_MAX_FILE_BYTES = 200_000
_MAX_FILES = 2000


def should_index_file(path: str, size_bytes: int) -> bool:
    """True si `path` merece indexarse en el mapa de conocimiento."""
    if size_bytes > _MAX_FILE_BYTES:
        return False
    segments = path.split("/")
    if any(seg in _EXCLUDED_DIR_SEGMENTS for seg in segments[:-1]):
        return False
    lowered = path.lower()
    if any(lowered.endswith(suffix) for suffix in _EXCLUDED_FILENAME_SUFFIXES):
        return False
    return True


def select_files_to_index(paths_with_sizes: list[tuple[str, int]]) -> list[str]:
    """Filtra y prioriza -- código fuente antes que docs/config, rutas más
    superficiales antes que profundas, hasta `_MAX_FILES`. Un repo real
    puede tener muchísimos más ficheros de los que merece la pena mandar
    al LLM uno a uno; un tope explícito es mejor que un job que no termina
    nunca."""
    candidates = [p for p, size in paths_with_sizes if should_index_file(p, size)]

    def _priority(path: str) -> tuple[int, int, str]:
        language = _infer_language(path)
        is_doc_or_config = language in ("markdown", "yaml", "json", "toml", None)
        return (1 if is_doc_or_config else 0, path.count("/"), path)

    candidates.sort(key=_priority)
    return candidates[:_MAX_FILES]


def extract_symbols_and_imports(content: str, path: str) -> tuple[list[str], list[str]]:
    """`(symbols, imports)` de un fichero real completo -- mismas
    funciones que usa `chunking.py` para diffs, aplicadas directamente
    sobre contenido real en vez de reconstruido."""
    language = _infer_language(path)
    if language is None:
        return [], []
    ranges = ast_boundaries.top_level_ranges(content, language)
    lines = content.splitlines()
    symbols: list[str] = []
    for start, _end in ranges:
        if 1 <= start <= len(lines):
            symbols.append(lines[start - 1].strip()[:120])
    imports = sorted(ast_boundaries.import_specifiers(content, language))
    return symbols, imports


def build_repo_import_graph(files: dict[str, tuple[str, str | None]]) -> dict[str, set[str]]:
    """Grafo no dirigido `path -> {paths relacionados}` para el repo
    COMPLETO -- `files` es `{path: (content, language)}`. Mismo criterio de
    correlación que `chunking.build_reference_graph`: un import que
    contiene el "stem" (nombre sin extensión) de otro fichero del repo
    cuenta como arista."""
    graph: dict[str, set[str]] = dict.fromkeys(files, set())
    stems = {path: path.rsplit("/", 1)[-1].split(".")[0] for path in files}
    for path, (content, language) in files.items():
        if language is None:
            continue
        refs = ast_boundaries.import_specifiers(content, language)
        if not refs:
            continue
        for other_path, other_stem in stems.items():
            if other_path == path or not other_stem:
                continue
            if any(other_stem in ref for ref in refs):
                graph[path].add(other_path)
                graph[other_path].add(path)
    return graph


# Ficheros "marcadores" que delatan el tipo de proyecto sin necesitar
# ninguna llamada de LLM -- barato y fiable, a diferencia de pedírselo al
# modelo (que además tendría que ver TODO el repo a la vez para acertar).
_PROJECT_TYPE_MARKERS: dict[str, str] = {
    "pyproject.toml": "Python (Poetry/PEP 621)",
    "setup.py": "Python (setuptools)",
    "package.json": "Node.js/JavaScript",
    "go.mod": "Go",
    "Cargo.toml": "Rust",
    "pom.xml": "Java (Maven)",
    "build.gradle": "Java/Kotlin (Gradle)",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
}


def _infer_project_type(paths: list[str]) -> str:
    basenames = {p.rsplit("/", 1)[-1] for p in paths}
    for marker, label in _PROJECT_TYPE_MARKERS.items():
        if marker in basenames:
            return label
    return "desconocido"


def _dominant_languages(paths: list[str], limit: int = 4) -> str:
    counts = Counter(lang for p in paths if (lang := _infer_language(p)) is not None)
    return ", ".join(lang for lang, _ in counts.most_common(limit)) or "desconocido"


def _build_module_breakdown(
    selected_paths: list[str], categories: dict[str, str], summaries_text: dict[str, str]
) -> list[dict[str, Any]]:
    """Agrupa por directorio de primer nivel -- cada "módulo" es una
    entrada con nombre, nº de ficheros, categoría dominante y una muestra
    de 2 resúmenes reales, sin necesitar ninguna llamada de LLM extra."""
    by_dir: dict[str, list[str]] = {}
    for path in selected_paths:
        top_dir = path.split("/", 1)[0] if "/" in path else "(raíz)"
        by_dir.setdefault(top_dir, []).append(path)

    breakdown = []
    for name, paths in sorted(by_dir.items(), key=lambda kv: -len(kv[1])):
        dominant_category = Counter(categories[p] for p in paths).most_common(1)[0][0]
        sample = [summaries_text[p] for p in paths[:2]]
        breakdown.append(
            {
                "name": name,
                "file_count": len(paths),
                "dominant_category": dominant_category,
                "sample_summaries": sample,
            }
        )
    return breakdown


def _build_overview(
    llm_client: LLMClient,
    repo_path: str,
    project_type: str,
    languages: str,
    module_breakdown: list[dict[str, Any]],
) -> str:
    modules_text = "\n".join(
        f"- {m['name']}/ ({m['file_count']} ficheros, {m['dominant_category']}): "
        + " · ".join(str(s) for s in m["sample_summaries"])
        for m in module_breakdown[:30]
    )
    system_prompt = (
        "Eres un arquitecto de software escribiendo la sección 'Arquitectura' de la "
        "documentación de un repositorio para otro ingeniero que nunca lo ha visto. "
        "Basándote SOLO en el desglose de módulos que te doy, escribe una descripción "
        "en markdown (encabezados ## por sección): qué hace el proyecto, cómo está "
        "organizado, y qué módulos parecen más sensibles desde el punto de vista de "
        "seguridad (auth, pagos, ejecución de comandos, etc.) si los hay. "
        "3-6 párrafos, sin inventar detalles que no se deduzcan del desglose."
    )
    user_prompt = (
        f"Repositorio: {repo_path}\nTipo de proyecto: {project_type}\n"
        f"Lenguajes dominantes: {languages}\n\nMódulos:\n{modules_text}"
    )
    overview = llm_client.synthesize_text(system_prompt, user_prompt)
    return overview or f"Mapa de {repo_path} construido, pero la síntesis de arquitectura falló."


def index_repo_files(monitored_repo_id: str, repo_path: str, files: dict[str, str]) -> None:
    """Punto de entrada único del indexado -- `files` es `{path: contenido}`
    del repo COMPLETO, ya obtenido por quien llama (vía la API de GitHub en
    `tasks.py::build_repo_knowledge_graph`, o desde un snapshot subido de
    un servidor Git propio en `api/routers/hooks.py`) -- de ahí en
    adelante el pipeline es idéntico para los dos orígenes. Nunca lanza:
    cualquier fallo deja `RepoArchitectureSummary.status="error"` con el
    motivo, no tumba el proceso que llama."""
    with next(get_session()) as session:
        summary_row = session.exec(
            select(RepoArchitectureSummary).where(
                RepoArchitectureSummary.monitored_repo_id == monitored_repo_id
            )
        ).first()
        if summary_row is None:
            summary_row = RepoArchitectureSummary(
                id=str(uuid4()), monitored_repo_id=monitored_repo_id
            )
            session.add(summary_row)
        summary_row.status = "building"
        summary_row.error_message = None
        session.commit()

        try:
            _run_indexing(session, monitored_repo_id, repo_path, files, summary_row)
        except Exception as exc:  # noqa: BLE001 -- ver docstring: nunca debe propagar
            logger.exception("Fallo indexando el mapa de conocimiento de %s", repo_path)
            summary_row.status = "error"
            summary_row.error_message = str(exc)[:500]
            session.commit()


def _run_indexing(
    session: Session,
    monitored_repo_id: str,
    repo_path: str,
    files: dict[str, str],
    summary_row: RepoArchitectureSummary,
) -> None:
    llm_client = build_llm_client()

    paths_with_sizes = [(p, len(c.encode("utf-8"))) for p, c in files.items()]
    selected_paths = select_files_to_index(paths_with_sizes)

    languages_by_path: dict[str, str | None] = {}
    symbols_by_path: dict[str, list[str]] = {}
    imports_by_path: dict[str, list[str]] = {}
    for path in selected_paths:
        content = files[path]
        symbols, imports = extract_symbols_and_imports(content, path)
        languages_by_path[path] = _infer_language(path)
        symbols_by_path[path] = symbols
        imports_by_path[path] = imports

    def _summarize(path: str) -> tuple[str, str, str]:
        fs = llm_client.summarize_file(path, files[path], symbols_by_path[path])
        return path, fs.category, fs.summary

    is_local_provider = os.environ.get("WATCHGATE_LLM_PROVIDER", "anthropic") == "local"
    summary_workers = _SUMMARY_WORKERS_LOCAL if is_local_provider else _SUMMARY_WORKERS

    categories: dict[str, str] = {}
    summaries_text: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=summary_workers) as pool:
        for path, category, summary in pool.map(_summarize, selected_paths):
            categories[path] = category
            summaries_text[path] = summary

    # Reintento en serie SOLO para los que degradaron a "unknown" por
    # timeout de cola en el primer pase -- un servidor local sobrecargado
    # un instante puede estar libre un segundo después. Sin concurrencia
    # de por medio (max_workers=1), así que no vuelve a sufrir el mismo
    # problema; como son pocos (normalmente un puñado, no el repo entero),
    # el coste en tiempo es bajo comparado con lo que se gana en cobertura
    # real de resúmenes.
    degraded_paths = [
        p for p in selected_paths if summaries_text[p].startswith("Sin resumen disponible")
    ]
    if degraded_paths:
        logger.info(
            "Reintentando en serie %d/%d ficheros que degradaron a 'unknown' en el primer pase.",
            len(degraded_paths),
            len(selected_paths),
        )
        for path in degraded_paths:
            _, category, summary = _summarize(path)
            categories[path] = category
            summaries_text[path] = summary

    import_graph = build_repo_import_graph(
        {p: (files[p], languages_by_path[p]) for p in selected_paths}
    )

    # Reindexado = reemplazar entero -- v1 no hace incremental por
    # content_hash todavía (ver comentario del campo en models.py).
    # `delete()` de SQLModel tipa peor que `select()` para mypy --strict
    # (comprobado: el `select().where(...)` equivalente más abajo no
    # necesita este ignore); no es un error real, es un hueco del stub.
    session.exec(
        delete(RepoGraphEdge).where(
            RepoGraphEdge.monitored_repo_id == monitored_repo_id  # type: ignore[arg-type]
        )
    )
    session.exec(
        delete(RepoGraphNode).where(
            RepoGraphNode.monitored_repo_id == monitored_repo_id  # type: ignore[arg-type]
        )
    )
    session.commit()

    node_ids: dict[str, str] = {}
    nodes = []
    for path in selected_paths:
        node_id = str(uuid4())
        node_ids[path] = node_id
        content = files[path]
        nodes.append(
            RepoGraphNode(
                id=node_id,
                monitored_repo_id=monitored_repo_id,
                file_path=path,
                language=languages_by_path[path],
                category=categories[path],
                summary=summaries_text[path],
                symbols=json.dumps(symbols_by_path[path][:30]),
                imports=json.dumps(imports_by_path[path][:30]),
                loc=content.count("\n") + 1,
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                embedding_id=node_id,
            )
        )
    if nodes:
        session.add_all(nodes)
        session.commit()

    if selected_paths:
        chroma_client = get_chroma_client(DEFAULT_INDEX_PATH)
        collection = chroma_client.get_or_create_collection(
            name=f"repo_graph_{monitored_repo_id}", metadata={"hnsw:space": "cosine"}
        )
        model = _get_embedding_model()
        docs = [summaries_text[p] for p in selected_paths]
        embeddings = model.encode(docs).tolist()
        collection.upsert(
            ids=[node_ids[p] for p in selected_paths],
            embeddings=embeddings,
            documents=docs,
            metadatas=[{"file_path": p, "category": categories[p]} for p in selected_paths],
        )

    edges = []
    seen_pairs: set[tuple[str, str]] = set()
    for path, neighbors in import_graph.items():
        if path not in node_ids:
            continue
        for neighbor in neighbors:
            if neighbor not in node_ids:
                continue
            first, second = sorted((path, neighbor))
            pair = (first, second)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            edges.append(
                RepoGraphEdge(
                    id=str(uuid4()),
                    monitored_repo_id=monitored_repo_id,
                    source_node_id=node_ids[pair[0]],
                    target_node_id=node_ids[pair[1]],
                    edge_type="import",
                )
            )
    if edges:
        session.add_all(edges)
        session.commit()

    project_type = _infer_project_type(selected_paths)
    languages = _dominant_languages(selected_paths)
    module_breakdown = _build_module_breakdown(selected_paths, categories, summaries_text)
    overview = _build_overview(llm_client, repo_path, project_type, languages, module_breakdown)

    summary_row.overview = overview
    summary_row.project_type = project_type
    summary_row.languages = languages
    summary_row.module_breakdown_json = json.dumps(module_breakdown)
    summary_row.node_count = len(nodes)
    summary_row.edge_count = len(edges)
    summary_row.status = "ready"
    summary_row.built_at = datetime.now(UTC)
    session.commit()
