"""Suite de aceptación end-to-end (spec §14).

Llama de verdad a la API de Gemini y usa git real -- no corre con `pytest`/
`pytest -q` por defecto (marcada `integration`, deseleccionada por el
`addopts` de `pyproject.toml`). Para ejecutarla explícitamente:

    poetry run pytest tests/integration/test_cases.py -m integration -v
"""

from __future__ import annotations

import json

import pytest

from tests.integration.pipeline_runner import DEFAULT_THRESHOLDS, discover_cases, run_full_pipeline

pytestmark = pytest.mark.integration

# Mismo margen que _BORDERLINE_MARGIN en _semantic/layer.py: la capa semántica
# ya hace resampling (hasta 2 llamadas extra, se queda con el score más alto)
# cuando SU risk_score cae dentro de este margen de un umbral -- eso es
# varianza real y esperada del LLM entre ejecuciones, documentada en el
# propio layer.py. Aquí se usa el mismo margen sobre el score AGREGADO final
# solo para anotar el mensaje de fallo, no para reintentar ni para ablandar
# la aserción: un fallo cerca de threshold sigue siendo un fallo, pero el
# mensaje dice explícitamente que podría ser ruido de resampling y no una
# regresión real, en vez de dejar ambos casos indistinguibles.
_THRESHOLD_NOISE_MARGIN = 10


def _acceptable_semaforos(expected: dict[str, object]) -> set[str]:
    value = expected["semaforo"]
    return {value} if isinstance(value, str) else set(value)  # type: ignore[arg-type]


def _threshold_noise_hint(score: int) -> str:
    thresholds = (DEFAULT_THRESHOLDS["yellow"], DEFAULT_THRESHOLDS["red"])
    if any(abs(score - t) <= _THRESHOLD_NOISE_MARGIN for t in thresholds):
        return (
            " [score cerca de un umbral de semáforo: podría ser varianza real "
            "del resampling de la capa semántica (ver _BORDERLINE_MARGIN en "
            "_semantic/layer.py), no necesariamente una regresión -- vuelve a "
            "ejecutar solo este caso un par de veces antes de asumir que es un "
            "bug real]"
        )
    return ""


@pytest.mark.parametrize("case_dir", discover_cases(), ids=lambda p: p.name)
def test_case(case_dir):
    expected = json.loads((case_dir / "expected.json").read_text())
    result = run_full_pipeline(case_dir)

    acceptable = _acceptable_semaforos(expected)
    hint = _threshold_noise_hint(result.score)
    assert result.semaforo.value in acceptable, (
        f"{case_dir.name}: semáforo {result.semaforo.value!r} (score {result.score}) "
        f"no está en lo esperado {acceptable}{hint}"
    )
    assert result.score >= expected.get("min_score", 0), (
        f"{case_dir.name}: score {result.score} por debajo del mínimo esperado "
        f"{expected.get('min_score', 0)}{hint}"
    )
