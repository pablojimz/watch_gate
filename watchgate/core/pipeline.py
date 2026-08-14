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
        layer_factories["semantic"] = lambda: SemanticLayer(
            llm_client, cost_control, client_init_error=client_init_error
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
