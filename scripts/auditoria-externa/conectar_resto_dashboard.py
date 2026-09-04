"""Conecta en modo 'audited' todos los repos de top-100-github-links.txt que
aun no esten en monitored_repos, replicando exactamente lo que hace
add_external_repo() (routers/repos.py) pero sin pasar por HTTP/auth -- pensado
para correr DENTRO del contenedor dashboard-worker (tiene acceso directo a la
BD y a la cola de RQ), no en el host.

NO se ejecuta solo -- lanzalo con conectar_resto_dashboard.sh desde el host
(hace el `docker cp` + `docker exec` en un solo paso), o a mano:

    docker cp top-100-github-links.txt watch_gate-dashboard-worker-1:/tmp/
    docker cp conectar_resto_dashboard.py watch_gate-dashboard-worker-1:/tmp/
    docker exec watch_gate-dashboard-worker-1 python3 /tmp/conectar_resto_dashboard.py

Antes de lanzarlo:
  - Comprueba que ORG_ID/USER_LOGIN de abajo siguen siendo la organizacion
    activa en el Dashboard (puede cambiar si inicias sesion con otra cuenta
    entretanto) -- o pasalos por env: WATCHGATE_BULK_ORG_ID / _USER_LOGIN.
  - Conecta CADA repo que falte de la lista y encola hasta 50 PRs abiertas
    por repo -- con los ~15 que ya estaban conectados al escribir esto,
    puede ser perfectamente miles de analisis en cola, cada uno con
    llamada real al LLM semantico (coste economico real). Con 3 workers en
    paralelo puede tardar horas en vaciarse.
  - Repos ya conectados en esa organizacion se saltan solos (no falla, ni
    duplica).
"""
from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import select

from watchgate.db.connection import get_session
from watchgate.db.models import MonitoredRepo
from watchgate.dashboard.backend.db import db_session as dashboard_db_session
from watchgate.dashboard.backend.db import upsert_role
from watchgate.dashboard.backend.tasks import ANALYSIS_JOB_TIMEOUT_SECONDS, get_queue, build_repo_knowledge_graph
from watchgate.service.repo_polling import RepoPollingService

# admin (personal) -- org activa del usuario en el Dashboard al escribir
# este script (04/09/2026). Verifica que sigue siendo la correcta antes de
# lanzarlo: SELECT id, name FROM organizations; en la BD del Dashboard.
ORG_ID = os.environ.get("WATCHGATE_BULK_ORG_ID") or "personal-6fc5d741-e10b-4e63-8b00-b314e52588f6"
USER_LOGIN = os.environ.get("WATCHGATE_BULK_USER_LOGIN") or "admin"

LINKS_FILE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/top-100-github-links.txt"

with open(LINKS_FILE) as f:
    lines = [l.strip() for l in f if l.strip()]

repo_paths: list[str] = []
for line in lines:
    url = line.split(". ", 1)[1].rstrip("/")
    repo_path = url.split("github.com/", 1)[1]
    repo_paths.append(repo_path)

print(f"Total en la lista: {len(repo_paths)}")

created, skipped, errored = 0, 0, 0
for repo_path in repo_paths:
    try:
        with next(get_session()) as session:
            existing = session.exec(
                select(MonitoredRepo).where(
                    MonitoredRepo.org_id == ORG_ID, MonitoredRepo.repo_path == repo_path
                )
            ).first()
            if existing:
                skipped += 1
                continue

            new_repo = MonitoredRepo(
                id=str(uuid4()),
                org_id=ORG_ID,
                vcs_connection_id=None,
                repo_path=repo_path,
                monitor_type="audited",
                status="active",
                created_at=datetime.now(UTC),
            )
            session.add(new_repo)
            session.commit()
            session.refresh(new_repo)

        with dashboard_db_session() as dash_conn:
            upsert_role(dash_conn, USER_LOGIN, repo_path, "mantenedor", org_id=ORG_ID)

        n_prs = RepoPollingService.poll_repo_by_id(new_repo.id)

        queue = get_queue()
        queue.enqueue(
            build_repo_knowledge_graph,
            new_repo.id,
            repo_path,
            job_id=f"repo-graph-{new_repo.id}",
            job_timeout=ANALYSIS_JOB_TIMEOUT_SECONDS,
        )

        created += 1
        print(f"[{created+skipped+errored}/{len(repo_paths)}] OK  {repo_path} -- {n_prs} PR(s) encoladas")
    except Exception as exc:  # noqa: BLE001
        errored += 1
        print(f"[{created+skipped+errored}/{len(repo_paths)}] ERROR {repo_path}: {exc}")

print(f"\nResumen: {created} conectados, {skipped} ya existian, {errored} fallaron")
