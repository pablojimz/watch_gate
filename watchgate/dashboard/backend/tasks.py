"""Configuración de colas y definición de tareas asíncronas."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor

import httpx
import redis
from rq import Queue
from sqlmodel import select

from watchgate.adapters.github_client import GitHubClient
from watchgate.config import load_config
from watchgate.core.diffparser import parse_diff_from_text
from watchgate.core.models import CommitAuthor
from watchgate.db.connection import get_session
from watchgate.db.models import MonitoredRepo, RepoArchitectureSummary, VCSConnection
from watchgate.service.quota import QuotaService

logger = logging.getLogger("watchgate.tasks")


def _repo_id_for(org_id: str, repo_path: str) -> str | None:
    """Busca el id de un `MonitoredRepo` por (org_id, repo_path) en una
    sesión NUEVA -- se llama desde los `except` de las tareas de escaneo de
    abajo, donde la sesión original de la tarea puede haber quedado en
    estado de transacción abortada por la propia excepción que se está
    gestionando (SQLAlchemy exige rollback antes de reutilizarla)."""
    with next(get_session()) as session:
        repo = session.exec(
            select(MonitoredRepo).where(
                MonitoredRepo.org_id == org_id, MonitoredRepo.repo_path == repo_path
            )
        ).first()
        return repo.id if repo else None


def run_managed_scan(
    repo_path: str,
    pr_number: int,
    installation_id: str,
    github_token: str | None = None,
    github_api_url: str | None = None,
) -> None:
    """Tarea principal para repositorios gestionados vía webhook."""
    with next(get_session()) as session:
        # Buscar la conexión y org a partir de installation_id
        vcs = session.exec(
            select(VCSConnection).where(VCSConnection.installation_id == installation_id)
        ).first()
        if not vcs or not vcs.org_id:
            return  # No registrado

        org_id = vcs.org_id

        try:
            from watchgate.dashboard.backend.db import db_session as dashboard_db_session
            from watchgate.dashboard.backend.db import resolve_github_credentials

            token, api_url = github_token, github_api_url
            if not token:
                # Credencial preferente del modo managed: el token efímero de
                # la propia instalación de la GitHub App (limitado a los
                # repos de ESA instalación, renovado solo, sin PATs de por
                # medio). Solo si la App está configurada en el servidor;
                # si no, cae a la cascada de PATs de siempre.
                from watchgate.adapters.github_app import (
                    get_installation_token,
                    github_app_configured,
                )

                if github_app_configured():
                    token = get_installation_token(installation_id)
            if not token or not api_url:
                with dashboard_db_session() as dash_conn:
                    res_tok, res_url = resolve_github_credentials(dash_conn, repo_path=repo_path)
                    token = token or res_tok
                    api_url = api_url or res_url

            client = GitHubClient(token, api_url=api_url)
            owner, repo_name = repo_path.split("/", 1)

            diff_text, metadata = client.get_pull_request_data(owner, repo_name, pr_number)

            # Construir autores
            author_login = metadata.get("user", {}).get("login", "unknown")
            author = CommitAuthor(
                name=author_login, email="unknown@example.com", login=author_login
            )
            parsed_diff = parse_diff_from_text(diff_text, authors=[author])

            # Análisis con control de cuota
            pipeline_metadata: dict[str, object] = {
                "pr_id": str(pr_number),
                "repo": repo_path,
                "author_login": author_login,
            }
            config = load_config()

            quota_service = QuotaService(session)
            result, is_degraded = quota_service.analyze_with_quota(
                diff=parsed_diff,
                metadata=pipeline_metadata,
                config=config,
                org_id=org_id,
                user_id=None,
                agent_id=None,
            )

            # 5. Insertar en la BD del Dashboard para que se pueda visualizar
            from watchgate.dashboard.backend.db import db_session as dashboard_db_session
            from watchgate.dashboard.backend.db import insert_aggregated, upsert_role

            with dashboard_db_session() as dash_conn:
                result.pr_id = str(pr_number)
                result.repo = repo_path
                insert_aggregated(dash_conn, result, author_login=author_login)

                # Buscamos el usuario de la DB SQLModel asociado para darle
                # permisos en el esquema del Dashboard
                from watchgate.db.models import User

                user_obj = session.exec(select(User).where(User.org_id == org_id)).first()
                if user_obj:
                    upsert_role(dash_conn, user_obj.name, repo_path, "admin_organizacion")

            # Actualizar last_scanned_at y limpiar la racha de fallos, si había
            repo_obj = session.exec(
                select(MonitoredRepo).where(
                    MonitoredRepo.org_id == org_id, MonitoredRepo.repo_path == repo_path
                )
            ).first()
            if repo_obj:
                from datetime import UTC, datetime

                repo_obj.last_scanned_at = datetime.now(UTC)
                repo_obj.consecutive_errors = 0

            session.commit()
        except Exception:
            # Sin este `except`, un token inválido/PR borrada/fallo de red de
            # GitHub o del propio análisis se propagaba sin más: no quedaba
            # reflejado en `MonitoredRepo` (ni `consecutive_errors` ni
            # `status`), no había log de aplicación (solo la traza cruda del
            # worker RQ) y el usuario no tenía forma de enterarse. Se
            # relanza a propósito DESPUÉS de registrar el fallo -- RQ debe
            # seguir marcando el job como failed (lo usan
            # `_enqueue_main_branch_scan`/`_poll_single_candidate` para
            # decidir si reintentar).
            logger.exception(
                "Fallo al analizar %s#%d en modo managed (org=%s)", repo_path, pr_number, org_id
            )
            session.rollback()
            repo_id = _repo_id_for(org_id, repo_path)
            if repo_id:
                from watchgate.service.repo_polling import RepoPollingService

                RepoPollingService.record_scan_outcome(repo_id, success=False)
            raise

        # En managed mode, publicamos un comentario en GitHub. Best-effort a
        # propósito: el escaneo YA se guardó con éxito (commit de arriba), así
        # que un fallo aquí (p. ej. el token no tiene permiso de escritura en
        # el repo) no debe marcar el repo como si el ANÁLISIS hubiera
        # fallado -- solo se registra para poder diagnosticarlo.
        try:
            from watchgate.core.comment_template import render_comment

            comment_body = render_comment(result)
            client.post_comment(owner, repo_name, pr_number, comment_body)
        except Exception:
            logger.exception(
                "El análisis de %s#%d se guardó bien pero no se pudo publicar el "
                "comentario en GitHub",
                repo_path,
                pr_number,
            )


def run_rag_sync() -> None:
    """Sincroniza avisos reales (GitHub Security Advisories) al corpus del
    RAG y reindexa si hubo cambios -- la mitad "fuentes externas" del RAG
    dinámico. La encola periódicamente el lifespan del dashboard-backend
    (ver main.py::_rag_sync_loop) y la ejecuta este worker, que es quien
    usa el índice en los análisis (pipeline -> retriever) y ya carga
    chromadb/sentence-transformers de todos modos.

    Imports diferidos: el backend encola esta tarea por su ruta con puntos
    (string), así que este módulo no debe arrastrar chromadb al proceso
    HTTP solo por definirla."""
    from watchgate.core.rag.indexer import CORPUS_DIR, build_index
    from watchgate.core.rag.threat_feed import sync_advisories_to_corpus

    written = sync_advisories_to_corpus(CORPUS_DIR)
    if not written:
        logger.info("RAG sync: sin avisos nuevos ni actualizados -- no se reindexa.")
        return
    count = build_index()
    logger.info(
        "RAG sync: %d avisos nuevos/actualizados en el corpus, %d fragmentos reindexados.",
        len(written),
        count,
    )


def purge_old_scores(retention_days: int) -> None:
    """Borra el histórico de `pr_scores` más antiguo que `retention_days`
    -- petición explícita: no acumular para siempre, mantener el
    Dashboard "serio" (sin PRs de hace meses/años engordando la lista y
    las métricas). La encola periódicamente el lifespan del
    dashboard-backend (ver main.py::_score_retention_loop), mismo patrón
    que run_rag_sync."""
    from watchgate.dashboard.backend import db as database

    with database.db_session() as conn:
        deleted = database.delete_scores_older_than(conn, retention_days)
    if deleted:
        logger.info(
            "Purga de retención: %d filas de pr_scores más antiguas de %d días borradas.",
            deleted,
            retention_days,
        )


def run_feedback_indexing(case_id: str, title: str, narrative: str, verdict: str) -> None:
    """Indexa en la colección de feedback del RAG un caso confirmado por
    revisión humana -- la mitad "aprendizaje propio" del RAG dinámico.

    En el worker y no en el request HTTP del dashboard a propósito:
    `add_confirmed_case` embebe el texto con sentence-transformers (carga
    de modelo en la primera llamada), demasiado pesado para responder a un
    click de "correcto"/"falso positivo"."""
    from typing import cast

    from watchgate.core.rag.feedback import Verdict, add_confirmed_case

    if verdict not in ("true_positive", "false_positive"):
        logger.warning("Feedback RAG: verdict desconocido %r, se ignora.", verdict)
        return
    fragments = add_confirmed_case(
        case_id=case_id, title=title, narrative=narrative, verdict=cast(Verdict, verdict)
    )
    logger.info(
        "Feedback RAG: caso %s indexado como %s (%d fragmentos).", case_id, verdict, fragments
    )


_REDIS_URL = os.environ.get("WATCHGATE_REDIS_URL", "redis://localhost:6379/0")


def get_redis_conn() -> redis.Redis:
    return redis.from_url(_REDIS_URL)


def get_queue() -> Queue:
    return Queue(connection=get_redis_conn())


# pr_id sintético para el escaneo de línea base de la rama por defecto
# (run_main_branch_scan) -- nunca colisiona con un número de PR real de
# GitHub (siempre entero, siempre >= 1). En la BD del dashboard,
# _pr_number_from_pr_id() lo mapea a pr_number=0 (sin dígitos en "main"),
# que por el mismo motivo tampoco puede colisionar con una PR real.
MAIN_BRANCH_SCAN_PR_ID = "main"


def run_main_branch_scan(
    repo_path: str,
    org_id: str,
    vcs_connection_id: str | None,
    user_login: str | None = None,
    github_token: str | None = None,
    github_api_url: str | None = None,
) -> None:
    """Escaneo de línea base: analiza TODO el contenido actual de la rama
    por defecto (no una PR concreta), disparado UNA VEZ al dar de alta un
    repositorio en auditoría externa -- ver
    routers/repos.py:add_external_repo. Dar de alta un repo con historial
    ya existente sin esto deja ese código de fondo completamente sin
    auditar hasta que alguien abra la primera PR nueva; esto da una foto
    de riesgo del estado ACTUAL del repo desde el primer momento.

    Mismo pipeline que `run_audit_scan` (comparten quota_service,
    inserción en la BD del dashboard, etc.) -- solo cambia de dónde sale
    el diff: `get_default_branch_scan_data` en vez de
    `get_pull_request_data`, y no hay `pr_number` real, así que se usa
    `MAIN_BRANCH_SCAN_PR_ID` como identificador."""
    with next(get_session()) as session:
        try:
            from watchgate.dashboard.backend.db import db_session as dashboard_db_session
            from watchgate.dashboard.backend.db import resolve_github_credentials

            token, api_url = github_token, github_api_url
            if not token or not api_url:
                with dashboard_db_session() as dash_conn:
                    res_tok, res_url = resolve_github_credentials(
                        dash_conn, user_login=user_login, repo_path=repo_path
                    )
                    token = token or res_tok
                    api_url = api_url or res_url

            client = GitHubClient(token, api_url=api_url)
            owner, repo_name = repo_path.split("/", 1)

            diff_text, metadata = client.get_default_branch_scan_data(owner, repo_name)

            author_login = metadata.get("user", {}).get("login", "unknown")
            author = CommitAuthor(
                name=author_login, email="unknown@example.com", login=author_login
            )
            parsed_diff = parse_diff_from_text(diff_text, authors=[author])

            reputation_metadata = None
            if author_login != "unknown":
                try:
                    reputation_metadata = client.get_reputation_metadata(
                        owner,
                        repo_name,
                        author_login,
                        head_sha=metadata.get("head", {}).get("sha"),
                    )
                except Exception:
                    pass

            pipeline_metadata: dict[str, object] = {
                "pr_id": MAIN_BRANCH_SCAN_PR_ID,
                "repo": repo_path,
                "author_login": author_login,
            }
            if reputation_metadata:
                pipeline_metadata["reputation"] = reputation_metadata
            config = load_config()

            quota_service = QuotaService(session)
            result, is_degraded = quota_service.analyze_with_quota(
                diff=parsed_diff,
                metadata=pipeline_metadata,
                config=config,
                org_id=org_id,
                user_id=None,
                agent_id=None,
            )

            from watchgate.dashboard.backend.db import db_session as dashboard_db_session
            from watchgate.dashboard.backend.db import insert_aggregated, upsert_role

            with dashboard_db_session() as dash_conn:
                result.pr_id = MAIN_BRANCH_SCAN_PR_ID
                result.repo = repo_path
                insert_aggregated(dash_conn, result, author_login=author_login)

                from watchgate.db.models import User

                user_obj = session.exec(select(User).where(User.org_id == org_id)).first()
                if user_obj:
                    upsert_role(dash_conn, user_obj.name, repo_path, "admin_organizacion")

            repo_obj = session.exec(
                select(MonitoredRepo).where(
                    MonitoredRepo.org_id == org_id, MonitoredRepo.repo_path == repo_path
                )
            ).first()
            if repo_obj:
                from datetime import UTC, datetime

                repo_obj.last_scanned_at = datetime.now(UTC)
                repo_obj.consecutive_errors = 0

            session.commit()
        except Exception:
            # Ver el `except` equivalente en `run_managed_scan` -- mismo
            # motivo: sin esto, un escaneo de línea base que falla
            # desaparece en silencio.
            logger.exception(
                "Fallo al analizar la rama principal de %s (org=%s)", repo_path, org_id
            )
            session.rollback()
            repo_id = _repo_id_for(org_id, repo_path)
            if repo_id:
                from watchgate.service.repo_polling import RepoPollingService

                RepoPollingService.record_scan_outcome(repo_id, success=False)
            raise


def run_audit_scan(
    repo_path: str,
    pr_number: int,
    org_id: str,
    vcs_connection_id: str | None,
    user_login: str | None = None,
    github_token: str | None = None,
    github_api_url: str | None = None,
) -> None:
    """Tarea principal de auditoría ejecutada por el worker."""
    with next(get_session()) as session:
        try:
            from watchgate.dashboard.backend.db import db_session as dashboard_db_session
            from watchgate.dashboard.backend.db import resolve_github_credentials

            token, api_url = github_token, github_api_url
            if not token or not api_url:
                with dashboard_db_session() as dash_conn:
                    res_tok, res_url = resolve_github_credentials(
                        dash_conn, user_login=user_login, repo_path=repo_path
                    )
                    token = token or res_tok
                    api_url = api_url or res_url

            # 2. Descargar Diff y Metadata
            client = GitHubClient(token, api_url=api_url)
            owner, repo_name = repo_path.split("/", 1)

            diff_text, metadata = client.get_pull_request_data(owner, repo_name, pr_number)

            # 3. Construir autores y metadatos de reputación
            author_login = metadata.get("user", {}).get("login", "unknown")
            author = CommitAuthor(
                name=author_login, email="unknown@example.com", login=author_login
            )
            parsed_diff = parse_diff_from_text(diff_text, authors=[author])

            reputation_metadata = None
            if author_login != "unknown":
                try:
                    reputation_metadata = client.get_reputation_metadata(
                        owner, repo_name, author_login, pr_number=pr_number
                    )
                except Exception:
                    pass

            # 4. Análisis con control de cuota
            pipeline_metadata: dict[str, object] = {
                "pr_id": str(pr_number),
                "repo": repo_path,
                "author_login": author_login,
            }
            if reputation_metadata:
                pipeline_metadata["reputation"] = reputation_metadata
            config = load_config()

            quota_service = QuotaService(session)
            # analyze_with_quota calls run_full_analysis and save_pr_score atomically
            result, is_degraded = quota_service.analyze_with_quota(
                diff=parsed_diff,
                metadata=pipeline_metadata,
                config=config,
                org_id=org_id,
                user_id=None,
                agent_id=None,
            )

            # 5. Insertar en la BD del Dashboard para que se pueda visualizar
            from watchgate.dashboard.backend.db import db_session as dashboard_db_session
            from watchgate.dashboard.backend.db import insert_aggregated, upsert_role

            with dashboard_db_session() as dash_conn:
                result.pr_id = str(pr_number)
                result.repo = repo_path
                insert_aggregated(dash_conn, result, author_login=author_login)

                # Buscamos el usuario de la DB SQLModel asociado para darle
                # permisos en el esquema del Dashboard
                from watchgate.db.models import User

                user_obj = session.exec(select(User).where(User.org_id == org_id)).first()
                if user_obj:
                    upsert_role(dash_conn, user_obj.name, repo_path, "admin_organizacion")

            # Actualizar last_scanned_at y limpiar la racha de fallos, si había
            repo_obj = session.exec(
                select(MonitoredRepo).where(
                    MonitoredRepo.org_id == org_id, MonitoredRepo.repo_path == repo_path
                )
            ).first()
            if repo_obj:
                from datetime import UTC, datetime

                repo_obj.last_scanned_at = datetime.now(UTC)
                repo_obj.consecutive_errors = 0

            session.commit()
        except Exception:
            # Ver el `except` equivalente en `run_managed_scan` -- mismo
            # motivo: sin esto, un token inválido/PR borrada/fallo de red
            # desaparecía en silencio sin dejar ningún rastro en
            # `MonitoredRepo` ni en ningún log de aplicación.
            logger.exception("Fallo al analizar %s#%d (org=%s)", repo_path, pr_number, org_id)
            session.rollback()
            repo_id = _repo_id_for(org_id, repo_path)
            if repo_id:
                from watchgate.service.repo_polling import RepoPollingService

                RepoPollingService.record_scan_outcome(repo_id, success=False)
            raise


def build_repo_knowledge_graph(
    monitored_repo_id: str,
    repo_path: str,
    github_token: str | None = None,
    github_api_url: str | None = None,
) -> None:
    """Construye el mapa de conocimiento (ficheros + resúmenes + grafo de
    imports + síntesis de arquitectura) de un repo de GitHub -- disparado
    al conectar un repo "audited"/"managed" (ver
    `routers/repos.py::add_external_repo`/`claim_installation`) o desde el
    botón manual "Reconstruir mapa". Solo aplica a repos GitHub-backed:
    para `monitor_type="git_server"` el mapa se construye desde
    `api/routers/hooks.py` a partir de un snapshot subido, no desde aquí
    (el Engine API no tiene credenciales de clon de un servidor Git ajeno,
    y esta tarea corre en el contenedor `dashboard-worker`, que tampoco).

    Descarga el árbol completo del repo vía la API de GitHub (`Contents`/
    `Git Trees`) y delega TODO el resto del pipeline (filtrado, resúmenes
    LLM, embeddings, grafo, persistencia) a
    `core/repo_graph.py::index_repo_files`, que es agnóstico de dónde
    salieron los ficheros -- por eso ese módulo vive en `core/` y no aquí:
    el import-linter prohíbe que `core` importe `adapters`/`dashboard`,
    así que la parte específica de GitHub (`GitHubClient`) tiene que
    quedarse en esta capa."""
    from watchgate.core.repo_graph import index_repo_files

    with next(get_session()) as session:
        repo = session.get(MonitoredRepo, monitored_repo_id)
    if repo is None or repo.monitor_type == "git_server":
        return

    # Fila "building" desde YA, antes de tocar la API de GitHub -- si algo
    # de lo de abajo falla (token inválido, repo movido/renombrado, rate
    # limit, red...), `index_repo_files` nunca llega a ejecutarse y antes
    # eso dejaba la tabla sin ninguna fila: el Dashboard seguía mostrando
    # "pendiente de construir" como si el botón "Reconstruir mapa" nunca
    # se hubiera pulsado, sin ningún error visible (reproducido en vivo
    # contra un repo real). Igual que el guard de `index_repo_files`, esto
    # nunca debe propagar -- un fallo de indexado no debe tumbar el
    # worker ni dejar el job en un estado sin explicación.
    with next(get_session()) as session:
        summary_row = session.exec(
            select(RepoArchitectureSummary).where(
                RepoArchitectureSummary.monitored_repo_id == monitored_repo_id
            )
        ).first()
        if summary_row is None:
            from uuid import uuid4

            summary_row = RepoArchitectureSummary(
                id=str(uuid4()), monitored_repo_id=monitored_repo_id
            )
            session.add(summary_row)
        summary_row.status = "building"
        summary_row.error_message = None
        session.commit()
        summary_row_id = summary_row.id  # capturado antes de que la sesión se cierre

    try:
        token, api_url = github_token, github_api_url
        if not token or not api_url:
            from watchgate.dashboard.backend.db import db_session as dashboard_db_session
            from watchgate.dashboard.backend.db import resolve_github_credentials

            with dashboard_db_session() as dash_conn:
                res_tok, res_url = resolve_github_credentials(dash_conn, repo_path=repo_path)
                token = token or res_tok
                api_url = api_url or res_url

        client = GitHubClient(token, api_url=api_url)
        owner, repo_name = repo_path.split("/", 1)
        metadata = client.get_repo_metadata(owner, repo_name)
        default_branch = metadata.get("default_branch", "main")

        tree = client.list_repo_tree(owner, repo_name, default_branch)
        blob_entries = [
            (entry["path"], entry.get("size", 0))
            for entry in tree
            if entry.get("type") == "blob" and "path" in entry
        ]

        from watchgate.core.repo_graph import select_files_to_index

        selected_paths = select_files_to_index(blob_entries)

        def _fetch(path: str) -> tuple[str, str | None]:
            return path, client.get_file_content(owner, repo_name, path, default_branch)

        files: dict[str, str] = {}
        # 16 en paralelo contra la Contents API agotaba el rate limit
        # incluso con token real (visto en vivo contra un repo real sin
        # token configurado: se comió el límite sin autenticar -- 60/h --
        # en unas pocas decenas de ficheros). 6 es más conservador sin
        # alargar mucho un repo de cientos de ficheros.
        with ThreadPoolExecutor(max_workers=6) as pool:
            for path, content in pool.map(_fetch, selected_paths):
                if content is not None:
                    files[path] = content
    except Exception as exc:  # noqa: BLE001 -- ver comentario de arriba: nunca debe propagar
        logger.exception(
            "Fallo obteniendo los ficheros de GitHub para el mapa de conocimiento de %s",
            repo_path,
        )
        message = str(exc)[:200]
        # GitHub responde 404 (no 403) a un repo PRIVADO sin token con
        # acceso -- por diseño, para no confirmar ni siquiera que existe.
        # Sin este mensaje, el error crudo ("Client error '404 Not Found'
        # for url ...") no deja nada claro por qué -- indistinguible de un
        # repo_path mal escrito. Verificado en vivo: sin
        # WATCHGATE_GITHUB_TOKEN/token personal/token de la VCSConnection,
        # esto es EXACTAMENTE lo que pasa con cualquier repo privado.
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404 and not token:
            message = (
                f"{message} -- Si '{repo_path}' es un repo privado, esto es esperado: "
                "sin token no hay forma de verlo (GitHub devuelve 404, no 403, para no "
                "confirmar ni que existe). Añade un token con acceso en Mi Cuenta -> "
                "Token personal de GitHub, o conéctalo vía GitHub App."
            )
        with next(get_session()) as session:
            row = session.get(RepoArchitectureSummary, summary_row_id)
            if row is not None:
                row.status = "error"
                row.error_message = message
                session.commit()
        return

    index_repo_files(monitored_repo_id, repo_path, files)


def index_uploaded_repo_snapshot(
    monitored_repo_id: str, repo_path: str, files: dict[str, str]
) -> None:
    """Contraparte de `build_repo_knowledge_graph` para repos de servidor
    Git propio -- `files` ya viene extraído del tarball subido por
    `docker/git-server-hooks/upload_snapshot.sh`
    (`api/routers/hooks.py::upload_repo_snapshot`), así que aquí no hay
    nada que descargar: se delega directo a `index_repo_files`.

    Corre en `dashboard-worker` (proceso separado), no en el Engine API --
    ese proceso enqueuea este job en vez de llamar a `index_repo_files`
    directamente, para no bloquear su propia capacidad de servir
    `/api/v1/analyze` (ni su healthcheck) mientras dura el indexado de un
    repo grande."""
    from watchgate.core.repo_graph import index_repo_files

    index_repo_files(monitored_repo_id, repo_path, files)
