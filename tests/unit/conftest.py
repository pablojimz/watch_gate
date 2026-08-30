"""conftest.py — aislamiento de tests unitarios frente al entorno real.

Auditoría: `WATCHGATE_DASHBOARD_DATABASE_URL` (una URL Postgres real,
siempre presente en los contenedores `engine-api`/`dashboard-backend` de
este despliegue) tiene prioridad sobre cualquier `tmp_path` que un test le
pase a `db_session()` (ver `watchgate/dashboard/backend/db.py::_database_url`
-- prioridad documentada e intencional para producción, pero letal para
tests que asumen aislamiento SQLite). Sin este fixture, un test que cree
usuarios o roles "de prueba" los escribe de verdad en la base de datos
Postgres compartida con el dashboard-backend real -- confirmado dos veces:
viendo un login creado en un test anterior ('javier-debug') filtrarse en
el resultado de un test que se creía aislado, y de nuevo escribiendo datos
de prueba reales (`unica`, `sola-a`, `org-a-admin`, ...) en esa misma base
de datos mientras se diagnosticaba este problema.

`autouse=True`: nadie tiene que acordarse de llamar a esto -- se aplica a
todo `tests/unit/`, donde SIEMPRE se asume aislamiento SQLite vía
`tmp_path`. Los tests de integración reales contra Postgres viven en
`tests/integration/` (fuera del alcance de este conftest) y configuran su
propia URL explícitamente."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_dashboard_db_from_real_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WATCHGATE_DASHBOARD_DATABASE_URL", raising=False)
