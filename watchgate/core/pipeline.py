"""Pipeline completo reutilizable: cortocircuito + capas reales + agregación.

Extraído de `cli.py` (§9) para que `watchgate/api/routers/analyze.py` (POST
/api/v1/analyze, invocado desde `entrypoint.sh` en la GitHub Action real) lo
use tal cual, en vez de duplicar el wiring de `cost_control`/`SemanticLayer`/
`shortcircuit`. La diferencia entre invocaciones está solo en cómo se
construyen `diff`/`metadata` (git local + argparse en la CLI; payload HTTP
recibido por el endpoint en la Action), no en cómo se analiza una vez
construidos.
"""

from __future__ import annotations

from watchgate.config import WatchGateConfig
from watchgate.core.aggregator import aggregate
from watchgate.core.cost_control import CostController
from watchgate.core.layers._semantic.layer import SemanticLayer
from watchgate.core.layers._semantic.llm_factory import build_llm_client
from watchgate.core.layers.base import safe_analyze
from watchgate.core.layers.vulnerabilities_layer import VulnerabilitiesLayer
from watchgate.core.models import AggregatedResult, LayerResult, NormalizedDiff
from watchgate.core.orchestrator import LayerFactory, ProgressCallback, run_analysis
from watchgate.core.shortcircuit import evaluate_shortcircuit


class _ConfigWithoutSemantic:
    """Wrapper helper para calcular el score parcial sin la capa semántica."""

    def __init__(self, full_config: WatchGateConfig) -> None:
        self.weights = {k: v for k, v in full_config.weights.items() if k != "semantic"}
        self.thresholds = full_config.thresholds


_REPO_GRAPH_QUERY_RESULTS = 8


def _check_blocked_author(repo_path: str, author_login: str, pr_id: str) -> AggregatedResult | None:
    """`None` si el autor no está bloqueado (o no se puede resolver nada
    -- nunca bloquea por error propio, un fallo aquí no debe tumbar un
    análisis normal); si lo está, un `AggregatedResult` ya cerrado en rojo
    para devolver de inmediato SIN instanciar ninguna capa (ni gastar
    presupuesto de LLM en absoluto).

    Resuelve la organización por `repo_path` (mismo criterio y misma
    tolerancia documentada en `_load_repo_graph_context`: en el caso raro
    de dos organizaciones con el mismo `repo_path`, el peor caso es
    comprobar el bloqueo de la organización equivocada, no una fuga de
    datos -- `ensure_api_key_repo_binding` ya validó el acceso real antes
    de llegar aquí)."""
    if not author_login:
        return None

    from datetime import UTC, datetime

    from sqlmodel import select

    from watchgate.core.models import Confidence, Semaforo, ThreatNature
    from watchgate.db.connection import get_session
    from watchgate.db.models import BlockedAuthor, MonitoredRepo

    try:
        with next(get_session()) as session:
            repo = session.exec(
                select(MonitoredRepo).where(MonitoredRepo.repo_path == repo_path)
            ).first()
            if repo is None:
                return None
            blocked = session.exec(
                select(BlockedAuthor).where(
                    BlockedAuthor.org_id == repo.org_id,
                    BlockedAuthor.author_login == author_login,
                )
            ).first()
            if blocked is None:
                return None
            reason = blocked.reason or "sin motivo registrado"
    except Exception:  # noqa: BLE001 -- comprobación opcional, nunca debe tumbar el análisis
        return None

    justification = (
        f"Autor '{author_login}' bloqueado en esta organización -- {reason}. "
        "Rechazado automáticamente sin ejecutar ningún análisis."
    )
    skipped_result = LayerResult(
        layer_name="blocklist",
        risk_score=100,
        justification=justification,
        confidence=Confidence.ALTA,
        threat_nature=ThreatNature.MALICIOUS,
        skipped=False,
    )
    return AggregatedResult(
        score=100,
        semaforo=Semaforo.ROJO,
        layer_results={"blocklist": skipped_result},
        weights_used={"blocklist": 1.0},
        effective_weights={"blocklist": 1.0},
        pr_id=pr_id,
        repo=repo_path,
        timestamp=datetime.now(UTC).isoformat(),
        threat_summary={
            ThreatNature.MALICIOUS.value: 1,
            ThreatNature.VULNERABILITY.value: 0,
            ThreatNature.UNCERTAIN.value: 0,
        },
    )


def _load_repo_graph_context(
    repo_path: str, diff: NormalizedDiff
) -> tuple[list[dict[str, object]], str | None, str | None] | None:
    """Ficheros del mapa de conocimiento del repo (`core/repo_graph.py`)
    relevantes para ESTE diff -- `None` si el repo no tiene mapa construido
    todavía (recién conectado, o de servidor Git propio sin snapshot
    subido) o si algo falla resolviéndolo; nunca lanza, es contexto
    opcional, no un requisito del análisis.

    Búsqueda por `repo_path` sin acotar por organización a propósito: es
    contexto para el prompt del LLM, no una decisión de control de acceso
    (esa la aplica `ensure_api_key_repo_binding` antes de llegar aquí) --
    en el caso raro de que dos organizaciones auditen el mismo repo_path,
    el peor caso es un contexto ligeramente ajeno en el prompt, no una
    fuga de datos entre organizaciones."""
    from sqlmodel import select

    from watchgate.db.connection import get_session
    from watchgate.db.models import MonitoredRepo, RepoArchitectureSummary

    try:
        with next(get_session()) as session:
            repo = session.exec(
                select(MonitoredRepo).where(MonitoredRepo.repo_path == repo_path)
            ).first()
            if repo is None:
                return None
            summary = session.exec(
                select(RepoArchitectureSummary).where(
                    RepoArchitectureSummary.monitored_repo_id == repo.id,
                    RepoArchitectureSummary.status == "ready",
                )
            ).first()
            if summary is None:
                return None
            repo_id = repo.id
            project_type = summary.project_type
            languages = summary.languages

        from watchgate.core.rag.indexer import DEFAULT_INDEX_PATH, get_chroma_client
        from watchgate.core.rag.retriever import _get_embedding_model

        collection = get_chroma_client(DEFAULT_INDEX_PATH).get_collection(f"repo_graph_{repo_id}")
        query_text = " ".join(fc.path for fc in diff.files)[:2000] or repo_path
        embedding = _get_embedding_model().encode([query_text]).tolist()
        result = collection.query(query_embeddings=embedding, n_results=_REPO_GRAPH_QUERY_RESULTS)
        metadatas = (result.get("metadatas") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        nodes = [
            {
                "file_path": meta.get("file_path", "?") if meta else "?",
                "category": meta.get("category", "unknown") if meta else "unknown",
                "summary": doc,
            }
            for meta, doc in zip(metadatas, documents, strict=False)
        ]
        return nodes, project_type, languages
    except Exception:  # noqa: BLE001 -- contexto opcional, nunca debe tumbar el análisis
        return None


def run_full_analysis(
    diff: NormalizedDiff,
    metadata: dict[str, object],
    config: WatchGateConfig,
    on_progress: ProgressCallback | None = None,
) -> AggregatedResult:
    """Ejecuta el pipeline completo: cortocircuito opcional (§11), capas
    activas reales (§9) con `CostController`/`SemanticLayer` reales cuando
    `weights["semantic"] > 0`, y agregación final (§10).

    `metadata` debe traer ya resueltas las señales que no puede calcular esta
    función por sí sola -- en particular `metadata["reputation"]` como un
    `ReputationMetadata` real (si falta, `ReputationLayer` se omite sola,
    no es un error aquí)."""
    repo_for_block_check = str(metadata.get("repo") or diff.repo_path or "")
    author_for_block_check = str(metadata.get("author_login") or "")
    if repo_for_block_check and author_for_block_check:
        blocked_result = _check_blocked_author(
            repo_for_block_check, author_for_block_check, str(metadata.get("pr_id", ""))
        )
        if blocked_result is not None:
            return blocked_result

    cost_control = None
    layer_factories: dict[str, LayerFactory] = {}

    # DepsLayer ya no necesita fábrica (sin argumentos obligatorios desde que
    # se le extrajo la consulta a OSV, ver vulnerabilities_layer.py) --
    # LAYER_REGISTRY["dependencies"]() por defecto en orchestrator.py basta.
    # max_dependency_checks sí sigue haciendo falta, pero ahora es
    # VulnerabilitiesLayer quien lo consume (max_osv_queries).
    if config.weights.get("vulnerabilities", 0) > 0:
        layer_factories["vulnerabilities"] = lambda: VulnerabilitiesLayer(
            max_osv_queries=config.max_dependency_checks
        )

    if config.weights.get("semantic", 0) > 0:
        cost_control = CostController(
            db_path=".watchgate/cost.db",
            max_diff_tokens=config.max_diff_tokens,
            monthly_budget_tokens=config.monthly_budget_tokens,
        )
        llm_client = None
        client_init_error: str | None = None
        try:
            llm_client = build_llm_client()
        except Exception as exc:  # noqa: BLE001 - un LLM mal configurado no debe tumbar el análisis: se degrada a "capa semántica omitida", no se propaga
            client_init_error = str(exc)
        repo_path_for_graph = str(metadata.get("repo") or diff.repo_path or "")
        repo_graph_result = (
            _load_repo_graph_context(repo_path_for_graph, diff) if repo_path_for_graph else None
        )
        repo_graph_context, repo_project_type, repo_languages = (
            repo_graph_result if repo_graph_result is not None else (None, None, None)
        )
        layer_factories["semantic"] = lambda: SemanticLayer(
            llm_client,
            cost_control,
            max_diff_tokens=config.max_diff_tokens,
            client_init_error=client_init_error,
            repo_graph_context=repo_graph_context,
            project_type=repo_project_type or "desconocido",
            languages=repo_languages or "desconocido",
        )

    try:
        if config.shortcircuit_enabled:
            partial_cfg = _ConfigWithoutSemantic(config)
            partial_res = run_analysis(diff, metadata, partial_cfg)
            shortcircuit_verdict = evaluate_shortcircuit(
                partial_results=partial_res.layer_results,
                weights=config.weights,
                diff=diff,
                thresholds=config.thresholds,
            )
            final_results = dict(partial_res.layer_results)
            if shortcircuit_verdict is not None:
                final_results["semantic"] = LayerResult(
                    layer_name="semantic",
                    risk_score=0,
                    justification="",
                    skipped=True,
                    skip_reason="Cortocircuito de extremo aplicado",
                )
            elif "semantic" in layer_factories:
                # Sin cortocircuito, solo falta la capa semántica -- las
                # demás (static/dependencies/vulnerabilities/reputation) ya
                # se ejecutaron arriba para `partial_res` y NO deben
                # repetirse. Antes se llamaba `run_analysis(diff, metadata,
                # config, ...)` completo otra vez aquí, re-ejecutando esas
                # capas desde cero (subprocesos de Semgrep, consultas OSV,
                # llamadas de red de reputación) sin ningún beneficio: el
                # cortocircuito existe para ahorrarse la llamada al LLM, no
                # para duplicar el resto del trabajo cuando no se dispara.
                final_results["semantic"] = safe_analyze(
                    layer_factories["semantic"](), diff, metadata
                )
            return aggregate(
                results=final_results,
                weights=config.weights,
                diff=diff,
                pr_id=str(metadata.get("pr_id", "")),
                repo=str(metadata.get("repo", "")),
                thresholds=config.thresholds,
            )
        return run_analysis(
            diff, metadata, config, layer_factories=layer_factories, on_progress=on_progress
        )
    finally:
        if cost_control is not None:
            cost_control.close()
