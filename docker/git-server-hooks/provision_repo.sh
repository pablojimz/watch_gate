#!/usr/bin/env bash
# Da de alta un repo de servidor Git propio (Forgejo local u otro) en
# WatchGate: crea (o reutiliza) una Organization/User de prueba, un
# MonitoredRepo (monitor_type="git_server") y una API key atada a ESE
# MonitoredRepo -- la puerta clave<->repo de
# watchgate/api/routers/analyze.py::ensure_api_key_repo_binding exige
# exactamente esa relación, no basta con pasar cualquier string como
# `monitored_repo_id` (ver la nota en docs/manual_git_hooks.md §5.3, cuyo
# ejemplo de un solo repo de prueba no crea el MonitoredRepo y por eso
# fallaría hoy con 403).
#
# Uso (con `docker compose up -d postgres engine-api` ya levantado):
#   ./docker/git-server-hooks/provision_repo.sh <owner>/<repo> [org_id]
#
# Imprime la API key nueva por stdout (única vez que se puede ver en claro
# -- solo se guarda su hash). Pásala a install.sh.
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Uso: $0 <owner>/<repo> [org_id]" >&2
    exit 1
fi

repo_path="$1"
org_id="${2:-local-git-server}"

# Auditoría: `repo_path`/`org_id` se interpolaban antes directamente
# dentro de un LITERAL de Python (`repo_path = '${repo_path}'`) -- una
# comilla simple en cualquiera de los dos rompía el literal e inyectaba
# código Python arbitrario, ejecutado dentro del contenedor engine-api
# con acceso real a la base de datos. Ahora viajan por variables de
# entorno (`docker compose exec -e ...`) y se leen con `os.environ` en
# vez de interpolarse en el código fuente -- un valor de entorno nunca se
# re-interpreta como sintaxis Python, se pase lo que se pase.
docker compose exec -T \
    -e WATCHGATE_PROVISION_REPO_PATH="$repo_path" \
    -e WATCHGATE_PROVISION_ORG_ID="$org_id" \
    engine-api python3 -c "
import os
from watchgate.db.connection import get_session
from watchgate.db.repository import create_organization, create_user, create_api_key
from watchgate.db.models import MonitoredRepo
from sqlmodel import select
import uuid

repo_path = os.environ['WATCHGATE_PROVISION_REPO_PATH']
org_id = os.environ['WATCHGATE_PROVISION_ORG_ID']

with next(get_session()) as session:
    org = create_organization(session, name=org_id, org_id=org_id)
    user = create_user(session, email=f'{org_id}@local', name=org_id, org_id=org.id)

    existing = session.exec(
        select(MonitoredRepo).where(
            MonitoredRepo.org_id == org.id, MonitoredRepo.repo_path == repo_path
        )
    ).first()
    if existing is None:
        repo = MonitoredRepo(
            id=str(uuid.uuid4()), org_id=org.id, repo_path=repo_path, monitor_type='git_server'
        )
        session.add(repo)
        session.commit()
        session.refresh(repo)
    else:
        repo = existing

    _, token = create_api_key(
        session, user_id=user.id, org_id=org.id, monitored_repo_id=repo.id,
        name=f'git-server hook: {repo_path}',
    )
    print(token)
"
