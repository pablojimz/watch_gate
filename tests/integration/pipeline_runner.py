"""Runner del pipeline completo para la suite de aceptación (spec §14).

Ejecuta las 5 capas reales registradas en `LAYER_REGISTRY` (static,
dependencies, vulnerabilities, reputation, semantic) -- `watchgate.core.
layers.__init__` las registra todas en cuanto se importa cualquier cosa
bajo `watchgate.core.layers` (este módulo importa `SemanticLayer` desde
ahí, lo que ya dispara el registro completo).

Nota histórica: `static_layer.py`/`deps_layer.py` sí estaban implementadas
desde hace tiempo, pero `watchgate/core/layers/__init__.py` nunca importaba
`static_layer` -- `LAYER_REGISTRY["static"]` no existía en ninguna
ejecución real (ni aquí ni en la CLI/Action), así que la capa estática
jamás llegó a ejecutarse contra un PR de verdad pese a tener peso 0.25 por
defecto. Corregido en `__init__.py`; los resultados de
`docs/validation_report.md` anteriores a ese fix (y a la separación de
`vulnerabilities_layer.py`) no reflejan las 5 capas reales -- hace falta
regenerar el informe (`generate_validation_report.py` contra la API real de
Gemini) para tener una cifra actualizada.

Convención de cada caso en `tests/cases/<nombre>/`:
    before/           árbol de ficheros del commit base (puede faltar si el
                      caso empieza de cero -- p. ej. un repo nuevo)
    after/            árbol de ficheros del commit head
    expected.json     {"semaforo": "rojo", "min_score": 66} (o una lista de
                      semáforos aceptables, p. ej. ["amarillo", "rojo"])
    metadata.json     ReputationMetadata en JSON

No se comitea un `repo/` con su propio `.git/`: git trata cualquier
subdirectorio con `.git` dentro como un submódulo (gitlink), no como
ficheros normales, así que un repo real de verdad no sobreviviría comiteado
tal cual dentro de este repo. En su lugar, `before/`/`after/` son árboles de
ficheros normales y corrientes; este runner materializa un repo real de dos
commits en un directorio temporal en cada ejecución (`base` = commit de
`before/`, `head` = commit de `after/`).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from watchgate.core.cost_control import CostController
from watchgate.core.diffparser import parse_diff
from watchgate.core.layers._semantic.layer import SemanticLayer
from watchgate.core.layers._semantic.llm_factory import build_llm_client
from watchgate.core.models import AggregatedResult, ReputationMetadata
from watchgate.core.orchestrator import LayerFactory, run_analysis

CASES_DIR = Path(__file__).resolve().parents[1] / "cases"

# Mismos pesos por defecto que config.py::_DEFAULT_WEIGHTS.
_WEIGHTS: dict[str, float] = {
    "static": 0.25,
    "dependencies": 0.10,
    "vulnerabilities": 0.10,
    "reputation": 0.15,
    "semantic": 0.40,
}
_THRESHOLDS: dict[str, int] = {"yellow": 40, "red": 70}


class _RunnerConfig:
    """Cumple el Protocol WatchGateConfig de orchestrator.py (weights/thresholds)."""

    def __init__(self, weights: dict[str, float], thresholds: dict[str, int]) -> None:
        self.weights = weights
        self.thresholds = thresholds


def discover_cases(cases_dir: Path = CASES_DIR) -> list[Path]:
    """Todo subdirectorio de `cases_dir` que tenga `expected.json`, orden estable."""
    if not cases_dir.is_dir():
        return []
    return sorted(p for p in cases_dir.iterdir() if p.is_dir() and (p / "expected.json").is_file())


def _load_reputation(case_dir: Path) -> ReputationMetadata:
    return ReputationMetadata.model_validate(json.loads((case_dir / "metadata.json").read_text()))


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)  # noqa: S603, S607


def _materialize_repo(case_dir: Path, repo_path: Path) -> None:
    """Construye un repo git real de dos commits en `repo_path` a partir de
    `before/`/`after/`. `before/` puede no existir (caso que empieza de cero:
    el primer commit simplemente añade todo lo que hay en `after/` menos lo
    que ya había en `before/`, aquí nada)."""
    repo_path.mkdir(parents=True, exist_ok=True)
    _git(repo_path, "init", "-q")
    _git(repo_path, "config", "user.email", "caso@watchgate.test")
    _git(repo_path, "config", "user.name", "WatchGate Validation Suite")

    before_dir = case_dir / "before"
    if before_dir.is_dir():
        shutil.copytree(before_dir, repo_path, dirs_exist_ok=True)
    (repo_path / ".gitkeep_base").write_text("")  # asegura que el commit base nunca esté vacío
    _git(repo_path, "add", "-A")
    _git(repo_path, "commit", "-q", "-m", "base")
    (repo_path / ".gitkeep_base").unlink()

    after_dir = case_dir / "after"
    for item in repo_path.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    shutil.copytree(after_dir, repo_path, dirs_exist_ok=True)
    _git(repo_path, "add", "-A")
    _git(repo_path, "commit", "-q", "-m", "head")


def run_full_pipeline(case_dir: Path) -> AggregatedResult:
    """Ejecuta el pipeline real (diffparser + reputation + semantic reales,
    orquestador + agregador reales) sobre un caso de `tests/cases/<nombre>/`.

    Cada llamada usa un `CostController` con una base de datos SQLite nueva en
    un directorio temporal: para esta suite queremos medir el comportamiento
    real del LLM en cada ejecución, no resultados servidos desde caché de una
    ejecución anterior."""
    repo_path = Path(tempfile.mkdtemp(prefix="watchgate_case_")) / "repo"
    _materialize_repo(case_dir, repo_path)
    diff = parse_diff(str(repo_path), base_sha="HEAD~1", head_sha="HEAD")
    reputation = _load_reputation(case_dir)
    metadata: dict[str, object] = {"repo": case_dir.name, "reputation": reputation}

    cost_db = tempfile.mkdtemp(prefix="watchgate_validation_") + "/cost.db"
    cost_control = CostController(
        db_path=cost_db, max_diff_tokens=8000, monthly_budget_tokens=2_000_000
    )
    try:
        llm_client = build_llm_client()
        layer_factories: dict[str, LayerFactory] = {
            "semantic": lambda: SemanticLayer(llm_client, cost_control),
        }
        config = _RunnerConfig(weights=_WEIGHTS, thresholds=_THRESHOLDS)
        return run_analysis(diff, metadata, config, layer_factories=layer_factories)
    finally:
        cost_control.close()
