"""Pipeline completo reutilizable: cortocircuito + capas reales + agregación.

Extraído de `cli.py` (§9) para que `adapters/github_action/main.py` (§12) lo
use tal cual, en vez de duplicar el wiring de `cost_control`/`SemanticLayer`/
`shortcircuit`. La diferencia entre invocaciones está solo en cómo se
construyen `diff`/`metadata` (git local + argparse en la CLI; evento de
GitHub + `GitHubClient` en la Action), no en cómo se analiza una vez
construidos.
"""

from __future__ import annotations

from watchgate.config import WatchGateConfig
from watchgate.core.aggregator import aggregate
from watchgate.core.cost_control import CostController
from watchgate.core.layers._semantic.layer import SemanticLayer
from watchgate.core.layers._semantic.llm_factory import build_llm_client
from watchgate.core.models import AggregatedResult, LayerResult, NormalizedDiff
from watchgate.core.orchestrator import LayerFactory, run_analysis
from watchgate.core.shortcircuit import evaluate_shortcircuit


class _ConfigWithoutSemantic:
    """Wrapper helper para calcular el score parcial sin la capa semántica."""

    def __init__(self, full_config: WatchGateConfig) -> None:
        self.weights = {k: v for k, v in full_config.weights.items() if k != "semantic"}
        self.thresholds = full_config.thresholds


def run_full_analysis(
    diff: NormalizedDiff, metadata: dict[str, object], config: WatchGateConfig
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

    if config.weights.get("semantic", 0) > 0:
        cost_control = CostController(
            db_path=".watchgate/cost.db",
            max_diff_tokens=config.max_diff_tokens,
            monthly_budget_tokens=config.monthly_budget_tokens,
        )
        try:
            llm_client = build_llm_client()
            layer_factories["semantic"] = lambda: SemanticLayer(llm_client, cost_control)
        except Exception:  # noqa: BLE001
            # Si falla el cliente LLM (ej. sin API key), safe_analyze lo aislará.
            pass

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
            if shortcircuit_verdict is not None:
                final_results = dict(partial_res.layer_results)
                final_results["semantic"] = LayerResult(
                    layer_name="semantic",
                    risk_score=0,
                    justification="",
                    skipped=True,
                    skip_reason="Cortocircuito de extremo aplicado",
                )
                return aggregate(
                    results=final_results,
                    weights=config.weights,
                    diff=diff,
                    pr_id=str(metadata.get("pr_id", "")),
                    repo=str(metadata.get("repo", "")),
                    thresholds=config.thresholds,
                )
            return run_analysis(diff, metadata, config, layer_factories=layer_factories)
        return run_analysis(diff, metadata, config, layer_factories=layer_factories)
    finally:
        if cost_control is not None:
            cost_control.close()
