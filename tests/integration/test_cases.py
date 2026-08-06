"""Suite de aceptación end-to-end (spec §14).

Llama de verdad a la API de Gemini y usa git real -- no corre con `pytest`/
`pytest -q` por defecto (marcada `integration`, deseleccionada por el
`addopts` de `pyproject.toml`). Para ejecutarla explícitamente:

    poetry run pytest tests/integration/test_cases.py -m integration -v
"""

from __future__ import annotations

import json

import pytest

from tests.integration.pipeline_runner import discover_cases, run_full_pipeline

pytestmark = pytest.mark.integration


def _acceptable_semaforos(expected: dict[str, object]) -> set[str]:
    value = expected["semaforo"]
    return {value} if isinstance(value, str) else set(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("case_dir", discover_cases(), ids=lambda p: p.name)
def test_case(case_dir):
    expected = json.loads((case_dir / "expected.json").read_text())
    result = run_full_pipeline(case_dir)

    acceptable = _acceptable_semaforos(expected)
    assert result.semaforo.value in acceptable, (
        f"{case_dir.name}: semáforo {result.semaforo.value!r} (score {result.score}) "
        f"no está en lo esperado {acceptable}"
    )
    assert result.score >= expected.get("min_score", 0), (
        f"{case_dir.name}: score {result.score} por debajo del mínimo esperado "
        f"{expected.get('min_score', 0)}"
    )
