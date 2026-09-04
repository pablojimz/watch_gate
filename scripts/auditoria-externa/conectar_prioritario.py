"""Conecta en modo 'audited' los repos de un fichero de lista (una ruta
owner/repo por línea) y encola sus PRs abiertas AL FRENTE de la cola de RQ
(`at_front=True`), por delante de lo que ya hubiera pendiente -- pensado
para priorizar un lote pequeño y concreto (p. ej. paquetes de gestores de
dependencias) sin esperar a que se vacíe una cola grande ya en marcha.

A diferencia de `conectar_resto_dashboard.py` (que usa
`RepoPollingService.poll_repo_by_id`, cola normal), este replica esa misma
lógica de encolado a mano para poder pasar `at_front=True` -- ver
`repo_polling.py::_poll_single_candidate` como referencia, mismo job_id,
mismos argumentos.

NO se ejecuta solo -- pensado para correr DENTRO del contenedor
dashboard-worker (acceso directo a BD/cola), vía `conectar_prioritario.sh`
o a mano:

    docker cp paquetes-gestores-dependencias.txt watch_gate-dashboard-worker-1:/tmp/
    docker cp conectar_prioritario.py watch_gate-dashboard-worker-1:/tmp/
    docker exec watch_gate-dashboard-worker-1 python3 /tmp/conectar_prioritario.py /tmp/paquetes-gestores-dependencias.txt

Repos ya conectados se saltan la creación, pero SUS PRs sin analizar
también se intentan encolar al frente igual que las de un repo nuevo (no
solo repos recién creados) -- así una repetición de esta lista siempre
prioriza lo que le pases, esté o no ya conectado el repo.
"""
from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import select

from watchgate.adapters.github_client import GitHubClient
from watchgate.dashboard.backend.db import db_session as dashboard_db_session
from watchgate.dashboard.backend.db import resolve_github_credentials, upsert_role
from watchgate.dashboard.backend.tasks import (
    ANALYSIS_JOB_TIMEOUT_SECONDS,
    build_repo_knowledge_graph,
    get_queue,
    run_audit_scan,
)
from watchgate.db.connection import get_session
from watchgate.db.models import MonitoredRepo
from watchgate.service.repo_polling import safe_job_id_part

ORG_ID = os.environ.get("WATCHGATE_BULK_ORG_ID") or "personal-6fc5d741-e10b-4e63-8b00-b314e52588f6"
USER_LOGIN = os.environ.get("WATCHGATE_BULK_USER_LOGIN") or "admin"

LINKS_FILE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/paquetes-gestores-dependencias.txt"

with open(LINKS_FILE) as f:
    repo_paths = [l.strip() for l in f if l.strip() and not l.startswith("#")]

print(f"Total en la lista: {len(repo_paths)}")

with dashboard_db_session() as dash_conn:
    token, api_url = resolve_github_credentials(dash_conn, user_login=USER_LOGIN, repo_path=None)

connected, already_connected, enqueued_total, errored = 0, 0, 0, 0

for repo_path in repo_paths:
    try:
        with next(get_session()) as session:
            existing = session.exec(
                select(MonitoredRepo).where(
                    MonitoredRepo.org_id == ORG_ID, MonitoredRepo.repo_path == repo_path
                )
            ).first()
            if existing:
                repo_id = existing.id
                vcs_connection_id = existing.vcs_connection_id
                already_connected += 1
            else:
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
                repo_id = new_repo.id
                vcs_connection_id = None
                connected += 1

                with dashboard_db_session() as dash_conn:
                    upsert_role(dash_conn, USER_LOGIN, repo_path, "mantenedor", org_id=ORG_ID)

                queue = get_queue()
                queue.enqueue(
                    build_repo_knowledge_graph,
                    repo_id,
                    repo_path,
                    job_id=f"repo-graph-{repo_id}",
                    job_timeout=ANALYSIS_JOB_TIMEOUT_SECONDS,
                )

        # Encolar PRs abiertas AL FRENTE, sea repo nuevo o ya existente.
        owner, repo_name = repo_path.split("/", 1)
        client = GitHubClient(token, api_url=api_url)
        prs = client.list_all_open_pull_requests(owner, repo_name, max_prs=50)

        queue = get_queue()
        n_enqueued = 0
        for pr in prs:
            pr_num = int(pr["number"])
            job_id = f"audit_pr-{safe_job_id_part(repo_path)}-{pr_num}"
            existing_job = queue.fetch_job(job_id)
            if existing_job:
                if existing_job.is_failed:
                    existing_job.delete()
                else:
                    continue  # ya encolada o ya analizada, no se reordena

            queue.enqueue(
                run_audit_scan,
                repo_path,
                pr_num,
                ORG_ID,
                vcs_connection_id,
                job_id=job_id,
                job_timeout=ANALYSIS_JOB_TIMEOUT_SECONDS,
                at_front=True,
            )
            n_enqueued += 1

        enqueued_total += n_enqueued
        estado = "nuevo" if repo_path not in [] else ""
        print(
            f"[{connected + already_connected}/{len(repo_paths)}] OK  {repo_path} -- "
            f"{len(prs)} PR(s) abiertas, {n_enqueued} encolada(s) al frente"
        )
    except Exception as exc:  # noqa: BLE001
        errored += 1
        print(f"ERROR {repo_path}: {exc}")

print(
    f"\nResumen: {connected} conectados nuevos, {already_connected} ya existían, "
    f"{enqueued_total} PRs encoladas al frente, {errored} fallaron"
)
