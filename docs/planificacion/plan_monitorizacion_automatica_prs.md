# Plan de Implementación: Monitorización Automática y Periódica de Pull Requests Externas (Especificación Final para Agente)

- **Fecha**: 2026-08-14
- **Estado**: Plan Auditado y Aprobado con Condiciones de Producción
- **Objetivo**: Automatizar la detección y análisis periódico de nuevas Pull Requests en repositorios de terceros (`monitor_type = "audited"`), con optimización HTTP (ETags), intervalos configurables por repositorio en el Dashboard, arquitectura limpia (servicio desacoplado), compatibilidad multi-base de datos (SQLModel/Postgres), protección contra errores de API, desduplicación limpia en Redis RQ y RBAC estricto.

---

## 1. Arquitectura y Flujo de Datos

```
                               ┌──────────────────────────────────────────────────────────┐
                               │  Proceso Scheduler (`scheduler.py` con Lock de Redis)     │
                               └────────────────────────────┬─────────────────────────────┘
                                                            │
                                                            ▼
                               ┌──────────────────────────────────────────────────────────┐
                               │  `RepoPollingService.poll_audited_repos_prs()`           │
                               │  1. Filtra repos candidatos (`audited`, `active`, token)  │
                               │  2. Cierra transacción DB antes de peticiones HTTP       │
                               └────────────────────────────┬─────────────────────────────┘
                                                            │
                                                            ▼
                               ┌──────────────────────────────────────────────────────────┐
                               │  `GitHubClient.list_recent_pull_requests_with_etag()`    │
                               └────────────────────────────┬─────────────────────────────┘
                                                            │
            ┌───────────────────────────────────────────────┼───────────────────────────────────────────────┐
            ▼ (HTTP 304 Not Modified)                       ▼ (HTTP 200 OK con PRs)                         ▼ (HTTP 404/403/429 Error)
┌───────────────────────────────────┐             ┌───────────────────────────────────┐             ┌───────────────────────────────────┐
│ Sin cambios en el repo.           │             │ Obtener PRs abiertas recientes.   │             │ Incrementar `consecutive_errors`. │
│ Actualizar `last_polled_at`.      │             │ Consultar `PRScore` con SQLModel. │             │ Si >= 5: cambiar `status=error`.  │
│ Resetear `consecutive_errors=0`.  │             │ Filtrar PRs ya analizadas/falladas│             │ Guardar en DB y continuar.        │
└───────────────────────────────────┘             └─────────────────┬─────────────────┘             └───────────────────────────────────┘
                                                                    │
                                                                    ▼
                                                  ┌───────────────────────────────────┐
                                                  │ Encolar `run_audit_scan` en RQ    │
                                                  │ ignorando jobs en estado `failed`.│
                                                  └───────────────────────────────────┘
```

---

## 2. Condiciones de Producción e Integridad

1. **Mecanismo de Despliegue del Scheduler con Distributed Lock**:
   * El script `watchgate/dashboard/backend/scheduler.py` se ejecutará como un proceso background independiente o mediante `rq-scheduler`.
   * Para evitar condiciones de carrera si existen múltiples réplicas del servicio web, se utiliza un **lock distribuido en Redis** (`redis_conn.lock("watchgate:polling_lock", timeout=120)`) antes de cada barrido.
2. **Gestión de Fallos HTTP y Repositorios Huérfanos**:
   * Campo `consecutive_errors: int = Field(default=0)` en `MonitoredRepo`.
   * Si la API de GitHub responde con errores 404, 403 o 422 de forma continuada, se incrementa `consecutive_errors`.
   * Al alcanzar 5 errores consecutivos, se cambia automáticamente `status = "error"` para detener el consumo inútil de peticiones. Una llamada exitosa resetea el contador a `0`.
3. **Manejo de Estados de Trabajo en Redis RQ**:
   * Al comprobar si un `job_id = f"audit_pr:{repo_path}:{pr_num}"` existe en Redis, si el trabajo está en estado `failed`, se elimina explícitamente (`existing_job.delete()`) para permitir que la PR se reintente limpiamente.
4. **Validación de Token para Modo Auditoría**:
   * Se requiere que el repositorio tenga un `vcs_connection_id` o que el sistema cuente con un token global de GitHub (`WATCHGATE_GITHUB_TOKEN`) para activar `auto_scan_prs`. Si no hay ningún token disponible, se omite el barrido anónimo para evitar agotar la cuota por IP pública (60 req/h).

---

## 3. Guía Paso a Paso para el Agente de Implementación

### Fase 1: Persistencia y Modelo de Datos (`watchgate/db/models.py`)

#### Archivo: `watchgate/db/models.py`
Extender `MonitoredRepo` con los nuevos campos:

```python
class MonitoredRepo(SQLModel, table=True):
    # Campos existentes...
    id: str = Field(primary_key=True)
    org_id: str = Field(foreign_key="organizations.id", index=True)
    vcs_connection_id: str | None = Field(foreign_key="vcs_connections.id", index=True, default=None)
    repo_path: str = Field(index=True)
    monitor_type: str = Field(default="managed")  # "managed" | "audited"
    status: str = Field(default="active")         # "active" | "paused" | "error"
    last_scanned_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # --- CAMPOS DE AUTOMATIZACIÓN, ETags Y RESILIENCIA ---
    auto_scan_prs: bool = Field(default=True)
    scan_interval_minutes: int = Field(default=30)
    prs_etag: str | None = Field(default=None)
    last_polled_at: datetime | None = Field(default=None)
    consecutive_errors: int = Field(default=0)
```

#### Archivo: `alembic/versions/<hash>_add_auto_scan_fields_to_monitoredrepo.py`
Generar e implementar la migración Alembic añadiendo las columnas con valores por defecto a `monitored_repos`.

---

### Fase 2: Cliente HTTP con ETags (`watchgate/adapters/github_client.py`)

#### Archivo: `watchgate/adapters/github_client.py`
Añadir el método `list_recent_pull_requests_with_etag`:

```python
def list_recent_pull_requests_with_etag(
    self, owner: str, repo: str, per_page: int = 10, etag: str | None = None
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Consulta PRs abiertas enviando `If-None-Match: <etag>`.
    
    Retorna:
    - (None, etag_actual) si responde HTTP 304 Not Modified.
    - (lista_prs, nuevo_etag) si responde HTTP 200 OK.
    """
    headers = dict(self._headers)
    if etag:
        headers["If-None-Match"] = etag

    params = {"state": "open", "sort": "created", "direction": "desc", "per_page": per_page}
    response = self._request("GET", f"/repos/{owner}/{repo}/pulls", params=params, headers=headers)
    
    if response.status_code == 304:
        return None, etag

    new_etag = response.headers.get("ETag")
    return list(response.json()), new_etag
```

---

### Fase 3: Servicio de Polling y Scheduler (`watchgate/service/repo_polling.py` & `scheduler.py`)

#### Archivo (Nuevo): `watchgate/service/repo_polling.py`
Implementar `RepoPollingService`:

```python
"""Servicio de polling de repositorios externos (Clean Architecture & SRP)."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from sqlmodel import select

from watchgate.adapters.github_client import GitHubClient
from watchgate.db.connection import get_session
from watchgate.db.models import MonitoredRepo, PRScore, VCSConnection


class RepoPollingService:
    @staticmethod
    def get_candidate_repos() -> list[dict[str, Any]]:
        """Obtiene la lista de repositorios candidatos cerrando la sesión de DB inmediatamente."""
        now = datetime.now(UTC)
        candidates = []
        default_token = os.environ.get("WATCHGATE_GITHUB_TOKEN")

        with next(get_session()) as session:
            repos = session.exec(
                select(MonitoredRepo).where(
                    MonitoredRepo.monitor_type == "audited",
                    MonitoredRepo.status == "active",
                    MonitoredRepo.auto_scan_prs == True,
                )
            ).all()

            for repo in repos:
                if repo.last_polled_at:
                    elapsed = (now - repo.last_polled_at.replace(tzinfo=UTC)).total_seconds() / 60.0
                    if elapsed < repo.scan_interval_minutes:
                        continue

                # Token específico o token global del sistema
                token = default_token
                if repo.vcs_connection_id:
                    vcs = session.exec(
                        select(VCSConnection).where(VCSConnection.id == repo.vcs_connection_id)
                    ).first()
                    if vcs and vcs.access_token:
                        token = vcs.access_token

                # Si no hay token disponible, omitir para no agotar la cuota por IP pública
                if not token:
                    continue

                candidates.append({
                    "id": repo.id,
                    "repo_path": repo.repo_path,
                    "org_id": repo.org_id,
                    "vcs_connection_id": repo.vcs_connection_id,
                    "prs_etag": repo.prs_etag,
                    "token": token,
                })

        return candidates

    @classmethod
    def poll_all_candidates(cls) -> int:
        """Efectúa el barrido con llamadas HTTP sin bloqueo de transacciones DB."""
        candidates = cls.get_candidate_repos()
        total_enqueued = 0
        now = datetime.now(UTC)

        for candidate in candidates:
            owner, repo_name = candidate["repo_path"].split("/", 1)
            client = GitHubClient(candidate["token"])

            try:
                prs, new_etag = client.list_recent_pull_requests_with_etag(
                    owner, repo_name, per_page=10, etag=candidate["prs_etag"]
                )
                success = True
            except Exception:
                prs, new_etag = None, None
                success = False

            # Actualizar estado HTTP y contador de errores en la BD
            with next(get_session()) as session:
                repo_db = session.get(MonitoredRepo, candidate["id"])
                if repo_db:
                    repo_db.last_polled_at = now
                    if success:
                        repo_db.consecutive_errors = 0
                        if new_etag:
                            repo_db.prs_etag = new_etag
                    else:
                        repo_db.consecutive_errors += 1
                        if repo_db.consecutive_errors >= 5:
                            repo_db.status = "error"
                    session.commit()

            if not success or prs is None:
                # Fallo o HTTP 304 Not Modified
                continue

            # Consultar PRs analizadas previamente con SQLModel
            with next(get_session()) as session:
                analyzed_pr_ids = set(
                    session.exec(
                        select(PRScore.pr_id).where(PRScore.repo == candidate["repo_path"])
                    ).all()
                )

            # Filtrar PRs nuevas
            new_prs = [p for p in prs if str(p["number"]) not in analyzed_pr_ids]
            
            from watchgate.dashboard.backend.tasks import get_queue, run_audit_scan
            queue = get_queue()

            for pr in new_prs[:5]:
                pr_num = int(pr["number"])
                job_id = f"audit_pr:{candidate['repo_path']}:{pr_num}"
                
                existing_job = queue.fetch_job(job_id)
                if existing_job:
                    if existing_job.is_failed:
                        existing_job.delete()  # Limpiar job fallido para permitir reintento
                    else:
                        continue

                queue.enqueue(
                    run_audit_scan,
                    candidate["repo_path"],
                    pr_num,
                    candidate["org_id"],
                    candidate["vcs_connection_id"],
                    job_id=job_id,
                )
                total_enqueued += 1

        return total_enqueued
```

#### Archivo (Nuevo): `watchgate/dashboard/backend/scheduler.py`
Subproceso ejecutor con lock distribuido en Redis:

```python
"""Bucle ejecutor del scheduler de polling con lock distribuido en Redis."""

import time
import logging
from watchgate.dashboard.backend.tasks import get_redis_conn
from watchgate.service.repo_polling import RepoPollingService

logger = logging.getLogger(__name__)

def run_scheduler_loop(interval_seconds: int = 300) -> None:
    redis_conn = get_redis_conn()
    logger.info("Iniciando scheduler loop de WatchGate...")

    while True:
        try:
            # Lock distribuido por 120s para prevenir ejecuciones simultáneas entre réplicas
            with redis_conn.lock("watchgate:polling_lock", timeout=120, blocking_timeout=2):
                enqueued = RepoPollingService.poll_all_candidates()
                if enqueued > 0:
                    logger.info(f"Scheduler encoló {enqueued} PRs para auditoría.")
        except Exception as exc:
            logger.warning(f"No se pudo adquirir lock o falló el barrido: {exc}")

        time.sleep(interval_seconds)

if __name__ == "__main__":
    run_scheduler_loop()
```

---

### Fase 4: REST API Backend (`watchgate/dashboard/backend/routers/repos.py`)

#### Archivo: `watchgate/dashboard/backend/routers/repos.py`
Añadir endpoint `PATCH /repos/external/{repo_id}` con verificación de permisos `require_role`:

```python
class MonitoredRepoUpdate(BaseModel):
    auto_scan_prs: bool | None = Field(default=None)
    scan_interval_minutes: int | None = Field(default=None)
    status: str | None = Field(default=None)


@router.patch("/{repo_id}", response_model=MonitoredRepoResponse)
def update_external_repo(
    repo_id: str,
    data: MonitoredRepoUpdate,
    current_user: CurrentUser,
    session: DBSession,
) -> Any:
    """Actualiza la configuración de automatización e intervalo de un repositorio externo."""
    user_login = normalize_login(current_user.login)
    db_user = _get_or_create_db_user(session, user_login)
    org_id = db_user.org_id
    assert org_id is not None

    repo = session.exec(
        select(MonitoredRepo).where(MonitoredRepo.id == repo_id, MonitoredRepo.org_id == org_id)
    ).first()

    if not repo:
        raise HTTPException(status_code=404, detail="Repositorio no encontrado")

    # Verificar rol del usuario en el repositorio
    from watchgate.dashboard.backend.db import db_session as dash_db_session, require_role
    with dash_db_session() as dash_conn:
        require_role(dash_conn, user_login, repo.repo_path, "mantenedor")

    if data.auto_scan_prs is not None:
        repo.auto_scan_prs = data.auto_scan_prs
    if data.scan_interval_minutes is not None:
        if data.scan_interval_minutes < 5:
            raise HTTPException(status_code=400, detail="El intervalo mínimo es de 5 minutos")
        repo.scan_interval_minutes = data.scan_interval_minutes
    if data.status is not None:
        if data.status not in ("active", "paused", "error"):
            raise HTTPException(status_code=400, detail="Estado inválido")
        repo.status = data.status

    session.commit()
    session.refresh(repo)
    return repo
```

---

### Fase 5: Interfaz Web Dashboard (`watchgate/dashboard/frontend/`)

1. **`src/api/client.ts`**:
   * Extender `MonitoredRepoResponse` con `auto_scan_prs`, `scan_interval_minutes`, `last_polled_at`, `consecutive_errors`.
   * Añadir método `updateExternalRepo(repoId, data)` con llamada `PATCH /repos/external/${repoId}`.
2. **`ExternalReposPage.tsx`**:
   * Añadir controles visuales: Switch para `auto_scan_prs`, selector desplegable de intervalo (15m, 30m, 1h, 2h, 24h) y Badge de estado (`status == "error"` resaltado en rojo con mensaje de error).

---

## 4. Plan de Pruebas y Validación (QA)

### Pruebas Unitarias (`tests/unit/test_repos_auto_scan.py`)
1. `test_github_client_etag`: Verificar HTTP 304 con `list_recent_pull_requests_with_etag`.
2. `test_repo_polling_service_candidates`: Verificar que solo repositorios activos con token entran en la lista de candidatos.
3. `test_repo_polling_service_error_handling`: Comprobar incremento de `consecutive_errors` y cambio a `status = "error"` tras 5 fallos.
4. `test_repo_polling_service_failed_job_cleanup`: Verificar borrado de trabajos fallidos en Redis RQ.
5. `test_repos_api_patch_rbac`: Comprobar rechazo 403 a usuarios con rol `revisor`.

---

## 5. Comandos de Verificación
```bash
# Executar linters y comprobación de tipos
poetry run ruff check .
poetry run mypy watchgate/

# Ejecutar la suite de tests unitarios
poetry run pytest tests/unit/test_repos_auto_scan.py
```
