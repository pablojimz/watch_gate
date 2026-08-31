"""feedback.py — endpoint de feedback humano + gestión de accesos (admin)."""

from __future__ import annotations

import logging
from typing import Annotated, TypedDict, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session, select

from watchgate.adapters.github_client import GitHubClient
from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.auth import CurrentUser, require_role
from watchgate.dashboard.backend.org_scope import (
    is_site_superadmin,
    resolve_caller_org_id,
    resolve_org_id_for_repo,
)
from watchgate.dashboard.backend.schemas import (
    AcceptScoreOut,
    DashboardUserCreate,
    DashboardUserOut,
    FeedbackIn,
    RepoRoleIn,
    RepoRoleOut,
    RoleName,
    ScoreOut,
    normalize_login,
)
from watchgate.db.connection import get_db_session
from watchgate.db.models import MonitoredRepo, VCSConnection

router = APIRouter(tags=["feedback"])

logger = logging.getLogger(__name__)

EngineDBSession = Annotated[Session, Depends(get_db_session)]


def _enqueue_feedback_indexing(score: ScoreOut) -> None:
    """Encola la incorporación de este veredicto humano al RAG (colección
    `feedback_cases`, la señal con hueco garantizado en el retriever).

    Cierra el bucle de feedback de la arquitectura: `add_confirmed_case`
    (core/rag/feedback.py) existía y estaba testeada, pero NADIE la llamaba
    desde producción -- marcar "correcto"/"falso positivo" solo tocaba la
    fila de la BD y el RAG nunca aprendía del propio historial de revisión.

    Best-effort a propósito: el feedback humano YA quedó guardado en la BD
    cuando esto se ejecuta; si Redis está caído, el click del revisor no
    debe fallar por no poder encolar el indexado."""
    verdict = "true_positive" if score.human_feedback == "correcto" else "false_positive"
    semantic = score.layer_results.get("semantic") or {}
    justification = ""
    if isinstance(semantic, dict):
        justification = str(semantic.get("justification") or "").strip()
    semaforo = getattr(score.semaforo, "value", score.semaforo)
    narrative_parts = [
        f"PR {score.pr_id} de {score.repo}: score {score.score}/100 ({semaforo}).",
    ]
    if justification:
        narrative_parts.append(justification)
    try:
        from watchgate.dashboard.backend.tasks import get_queue

        get_queue().enqueue(
            "watchgate.dashboard.backend.tasks.run_feedback_indexing",
            f"score_{score.id}",
            f"Feedback humano: PR {score.pr_id} en {score.repo}",
            "\n\n".join(narrative_parts),
            verdict,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "No se pudo encolar el indexado RAG del feedback del score %d "
            "(el feedback en sí ya quedó guardado).",
            score.id,
        )


@router.post("/scores/{score_id}/feedback", response_model=ScoreOut)
def submit_feedback(
    score_id: int, body: FeedbackIn, request: Request, user: CurrentUser
) -> ScoreOut:
    with database.db_session() as conn:
        existing = database.get_score(conn, score_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Score no encontrado")
        require_role(user, existing.repo, min_role="mantenedor", request=request)
        updated = database.set_feedback(conn, score_id, body.feedback)
    if updated is None:
        raise HTTPException(status_code=404, detail="Score no encontrado")
    _enqueue_feedback_indexing(updated)
    return updated


def _resolve_merge_client(
    engine_session: Session, repo_path: str
) -> tuple[GitHubClient, str] | None:
    """`None` si `repo_path` no tiene una `VCSConnection` real guardada
    (score ingerido solo vía `POST /scores` desde CI genérico, sin App/PAT
    conectado) o si esa conexión no tiene ningún token utilizable -- en
    ambos casos no hay nada que mergear de forma segura. Deliberadamente
    NO cae a `WATCHGATE_GITHUB_TOKEN`/`GITHUB_TOKEN` de entorno (a
    diferencia de `resolve_github_credentials`, pensado para lecturas):
    mergear un PR es una acción mutante y de alto impacto, así que solo se
    dispara con una credencial explícitamente atada a ESTE repo, nunca con
    un token ambiental que puede no tener nada que ver con la conexión que
    el usuario configuró en WatchGate.

    Envuelto en un `try` propio (no solo el de `_try_merge_pull_request`,
    que cubre la llamada HTTP a GitHub): un despliegue del dashboard sin
    la Engine DB migrada (solo ingesta vía `POST /scores`, sin
    `monitored_repos`/`vcs_connections` creadas) debe tratarse igual que
    "no hay conexión guardada", no reventar la aceptación con un
    `OperationalError`."""
    try:
        repo = engine_session.exec(
            select(MonitoredRepo).where(MonitoredRepo.repo_path == repo_path)
        ).first()
        if not repo or not repo.vcs_connection_id:
            return None
        vcs = engine_session.get(VCSConnection, repo.vcs_connection_id)
    except Exception:  # noqa: BLE001 -- ver docstring
        logger.warning(
            "No se pudo consultar la Engine DB para resolver credenciales de merge de %s",
            repo_path,
            exc_info=True,
        )
        return None
    if not vcs:
        return None

    token: str | None = None
    if vcs.installation_id:
        from watchgate.adapters.github_app import get_installation_token, github_app_configured

        if github_app_configured():
            token = get_installation_token(vcs.installation_id)
    if not token:
        token = vcs.access_token
    if not token:
        return None
    return GitHubClient(token), "https://api.github.com"


class _MergeResult(TypedDict):
    merge_attempted: bool
    merged: bool | None
    merge_message: str | None


def _try_merge_pull_request(engine_session: Session, repo_path: str, pr_id: str) -> _MergeResult:
    """Intenta mergear el PR real en GitHub tras aceptarlo -- ver
    `accept_score`. Devuelve los campos extra de `AcceptScoreOut`
    (`merge_attempted`/`merged`/`merge_message`); nunca lanza -- un fallo
    de merge (rama protegida, checks pendientes, conflictos, PR ya
    cerrado) no debe impedir que la aceptación humana quede registrada,
    solo se reporta para que el frontend lo muestre.

    `dict[str, object]` (el tipo anterior) hacía que mypy tratase
    `**merge_result` en `accept_score` como kwargs sin tipo alguno --
    con un TypedDict de los 3 campos exactos, `AcceptScoreOut(**merge_result)`
    sí type-checkea contra los campos reales del modelo."""
    if not pr_id.isdigit():
        # pr_id="main" (escaneo de rama principal), "local-push" (hook
        # pre-push local) o cualquier otro identificador que no sea un
        # número de PR real de GitHub -- no hay nada que mergear.
        return {"merge_attempted": False, "merged": None, "merge_message": None}

    resolved = _resolve_merge_client(engine_session, repo_path)
    if resolved is None:
        return {"merge_attempted": False, "merged": None, "merge_message": None}
    client, _api_url = resolved

    try:
        owner, repo_name = repo_path.split("/", 1)
        client.merge_pull_request(owner, repo_name, int(pr_id))
    except Exception as exc:  # noqa: BLE001 -- best-effort, ver docstring
        logger.warning(
            "No se pudo mergear %s#%s tras aceptarlo en el dashboard: %r", repo_path, pr_id, exc
        )
        return {
            "merge_attempted": True,
            "merged": False,
            "merge_message": (
                "No se pudo mergear en GitHub (rama protegida, checks pendientes, "
                "conflictos, o el PR ya no está abierto). El PR sigue quedando "
                "marcado como aceptado."
            ),
        }
    return {"merge_attempted": True, "merged": True, "merge_message": None}


@router.post("/scores/{score_id}/accept", response_model=AcceptScoreOut)
def accept_score(
    score_id: int, request: Request, user: CurrentUser, engine_session: EngineDBSession
) -> AcceptScoreOut:
    """Gate de aprobación manual: registra que `user` revisó este PR
    amarillo/rojo y decide seguir adelante a sabiendas del riesgo -- y, si
    el repo tiene una conexión real de GitHub guardada y el PR es real
    (no un escaneo de rama principal ni un análisis de hook local), lo
    mergea de verdad en GitHub. Antes "Aceptar" solo dejaba constancia en
    la BD del dashboard sin tocar GitHub para nada -- confuso para quien
    esperaba que aceptar un PR de riesgo lo mergeara de una vez."""
    with database.db_session() as conn:
        existing = database.get_score(conn, score_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Score no encontrado")
        require_role(user, existing.repo, min_role="mantenedor", request=request)
        updated = database.set_accepted(conn, score_id, user.login)
    if updated is None:
        raise HTTPException(status_code=404, detail="Score no encontrado")

    merge_result = _try_merge_pull_request(engine_session, updated.repo, updated.pr_id)
    return AcceptScoreOut(**updated.model_dump(), **merge_result)


@router.delete("/scores/{score_id}/accept", response_model=ScoreOut)
def unaccept_score(score_id: int, request: Request, user: CurrentUser) -> ScoreOut:
    with database.db_session() as conn:
        existing = database.get_score(conn, score_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Score no encontrado")
        require_role(user, existing.repo, min_role="mantenedor", request=request)
        updated = database.clear_accepted(conn, score_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Score no encontrado")
    return updated


@router.get("/admin/roles", response_model=list[RepoRoleOut])
def list_all_roles(
    request: Request, user: CurrentUser, engine_session: EngineDBSession
) -> list[RepoRoleOut]:
    # Auditoría (hallazgo crítico, corregido): antes devolvía TODOS los
    # roles de TODAS las organizaciones -- ahora acotado a la
    # organización real del llamador.
    org_id = resolve_caller_org_id(engine_session, user.login)
    with database.db_session() as conn:
        if not database.user_is_org_admin(conn, user.login, org_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Se requiere admin_organizacion",
            )
        rows = database.list_roles(conn, org_id=org_id)

    # `repo_roles` (Dashboard DB) es solo (user_login, repo, role) -- no
    # sabe si `repo` está conectado como repo externo, eso vive en
    # MonitoredRepo (Engine DB). Un solo IN(...) contra la Engine DB en
    # vez de una consulta por fila -- mismo motivo que compute_org_metrics
    # ya documenta para SELECT * vs columnas explícitas: evitar N
    # consultas donde una basta.
    distinct_repos = {r["repo"] for r in rows}
    monitor_types: dict[str, str] = {}
    if distinct_repos:
        monitored = engine_session.exec(
            select(MonitoredRepo).where(
                MonitoredRepo.repo_path.in_(distinct_repos)  # type: ignore[attr-defined]
            )
        ).all()
        for m in monitored:
            # Dos organizaciones distintas pueden auditar el mismo
            # repo_path (ver comentario en
            # routers/repos.py::_enqueue_main_branch_scan) -- si difieren
            # en monitor_type, se queda con el primero que aparezca; es
            # solo informativo en esta tabla, no una fuente de verdad de
            # a qué organización pertenece el rol.
            monitor_types.setdefault(m.repo_path, m.monitor_type)

    return [
        RepoRoleOut(
            user_login=r["user_login"],
            repo=r["repo"],
            role=cast(RoleName, r["role"]),
            monitor_type=monitor_types.get(r["repo"]),
        )
        for r in rows
    ]


def _require_role_manager(
    conn: Session,
    user_login: str,
    org_id: str,
    target_org_id: str | None,
    repo: str,
) -> bool:
    """`True` si `user_login` puede gestionar accesos de `repo` -- o bien
    `admin_organizacion` de la organización dueña (gestiona cualquier repo
    suyo), o bien `mantenedor` de ESE repo concreto (el "dueño del repo"
    del RBAC: gestiona SOLO lo suyo, nunca los repos de otros compañeros
    de la misma organización). `False` si `repo` no es de mi organización
    -- mismo fail-closed que antes, ahora también para el camino de
    mantenedor."""
    if target_org_id != org_id:
        return False
    if database.user_is_org_admin(conn, user_login, org_id):
        return True
    return database.get_role(conn, user_login, repo) == "mantenedor"


@router.put("/admin/roles", response_model=RepoRoleOut)
def upsert_role(
    body: RepoRoleIn, request: Request, user: CurrentUser, engine_session: EngineDBSession
) -> RepoRoleOut:
    """Concede (o cambia) el rol de `body.user_login` sobre `body.repo`.

    RBAC: dos perfiles pueden llegar aquí -- `admin_organizacion` (gestiona
    cualquier repo de su organización, incluida la concesión de nuevos
    `admin_organizacion`) y `mantenedor` del repo concreto (el "dueño del
    repo": puede añadir gente a SU repo, pero nunca conceder
    `admin_organizacion` -- eso sería auto-escalar el poder de un tercero
    por encima del suyo propio -- ni tocar el acceso de quien YA es
    `admin_organizacion` de la organización)."""
    org_id = resolve_caller_org_id(engine_session, user.login)
    # Auditoría: además de acotar la comprobación de admin, hay que
    # comprobar que `body.repo` sea de verdad un repo de MI organización
    # -- si no, un admin_organizacion (ya acotado) podría seguir
    # concediendo roles (incluido "admin_organizacion") sobre el repo de
    # OTRA organización con solo escribir su nombre en el body, sin que
    # `user_is_org_admin` lo detectase (esa comprobación es sobre quién
    # llama, no sobre a qué repo se refiere la petición).
    target_org_id = resolve_org_id_for_repo(engine_session, body.repo)
    with database.db_session() as conn:
        is_org_admin = database.user_is_org_admin(conn, user.login, org_id)
        if not _require_role_manager(conn, user.login, org_id, target_org_id, body.repo):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Se requiere ser mantenedor de este repo, o admin_organizacion",
            )
        if not is_org_admin:
            if body.role == "admin_organizacion":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Un mantenedor no puede conceder admin_organizacion",
                )
            if database.get_role(conn, body.user_login, body.repo) == "admin_organizacion":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Solo admin_organizacion puede modificar a otro admin_organizacion",
                )
        database.upsert_role(conn, body.user_login, body.repo, body.role, org_id=org_id)
    return RepoRoleOut(user_login=body.user_login, repo=body.repo, role=body.role)


@router.delete("/admin/roles/{user_login}/{repo:path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    user_login: str,
    repo: str,
    request: Request,
    user: CurrentUser,
    engine_session: EngineDBSession,
) -> None:
    """Revoca el acceso de `user_login` a `repo` -- mismo RBAC que
    `upsert_role`: admin_organizacion de cualquier repo suyo, o mantenedor
    de ESE repo (nunca puede quitarle el acceso a un admin_organizacion)."""
    org_id = resolve_caller_org_id(engine_session, user.login)
    target_org_id = resolve_org_id_for_repo(engine_session, repo)
    with database.db_session() as conn:
        is_org_admin = database.user_is_org_admin(conn, user.login, org_id)
        if not _require_role_manager(conn, user.login, org_id, target_org_id, repo):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Se requiere ser mantenedor de este repo, o admin_organizacion",
            )
        existing_role = database.get_role(conn, user_login, repo)
        if existing_role is None:
            raise HTTPException(status_code=404, detail="Rol no encontrado")
        if not is_org_admin and existing_role == "admin_organizacion":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo admin_organizacion puede revocar a otro admin_organizacion",
            )
        database.delete_role(conn, user_login, repo)


@router.get("/repos/{repo:path}/roles", response_model=list[RepoRoleOut])
def list_roles_for_repo(repo: str, request: Request, user: CurrentUser) -> list[RepoRoleOut]:
    """Colaboradores con acceso a ESTE repo -- versión acotada de
    `GET /admin/roles` (que exige `admin_organizacion` y lista TODA la
    organización) para que un `mantenedor` (dueño de repo, ver RBAC en
    `upsert_role`) pueda ver y gestionar el acceso de su propio repo sin
    necesitar visibilidad sobre el resto de repos de su organización."""
    require_role(user, repo, min_role="mantenedor", request=request)
    with database.db_session() as conn:
        rows = database.list_roles(conn, repo=repo)
    return [
        RepoRoleOut(user_login=r["user_login"], repo=r["repo"], role=cast(RoleName, r["role"]))
        for r in rows
    ]


@router.get("/admin/users", response_model=list[DashboardUserOut])
def list_all_users(request: Request, user: CurrentUser) -> list[DashboardUserOut]:
    """Cuentas locales (login/contraseña) del Dashboard -- distinto de
    `/admin/roles`: esto es la cuenta en sí (puede iniciar sesión con
    usuario/contraseña), aquello es qué repos puede ver/administrar una
    vez dentro. Un login puede tener roles asignados sin tener cuenta
    local aquí (entra por GitHub/OIDC) -- las dos tablas son
    independientes a propósito."""
    # Auditoría: `dashboard_users` (cuentas locales login/contraseña) no
    # tiene columna de organización -- es una tabla de INSTANCIA completa,
    # no por-organización, así que exige superadmin de sitio en vez de un
    # admin_organizacion (que tras acotarlo por org ya no tendría poder
    # real sobre cuentas que no son "suyas" de ningún modo verificable).
    if not is_site_superadmin(user.login):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere superadmin de sitio"
        )
    with database.db_session() as conn:
        users = database.list_users(conn)
        # Construir los DTOs DENTRO del `with`: `conn.close()` al salir
        # expira los objetos ORM (`expire_on_commit=True` por defecto), y
        # acceder a `.login`/`.display_name` después lanza
        # `DetachedInstanceError` -- reproducido en la revisión (mismo
        # motivo por el que `list_roles()` en db.py ya devuelve dicts en
        # vez de instancias ORM).
        return [DashboardUserOut(login=u.login, display_name=u.display_name) for u in users]


@router.post("/admin/users", response_model=DashboardUserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: DashboardUserCreate,
    request: Request,
    user: CurrentUser,
    engine_session: EngineDBSession,
) -> DashboardUserOut:
    if not is_site_superadmin(user.login):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere superadmin de sitio"
        )
    with database.db_session() as conn:
        if database.get_user(conn, body.login) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe una cuenta local con el login '{body.login}'",
            )
        database.upsert_user(conn, body.login, body.password, body.display_name)
        if body.repo and body.role:
            # Auditoría: el rol asignado aquí es sobre un repo real, que
            # pertenece a una organización real -- resolverla igual que en
            # upsert_role/delete_role, para que este admin_organizacion
            # concedido por un superadmin de sitio quede correctamente
            # acotado (org_id=None quedaría inerte por el diseño fail-closed
            # de user_is_org_admin, rompiendo silenciosamente el flujo).
            target_org_id = resolve_org_id_for_repo(engine_session, body.repo)
            database.upsert_role(conn, body.login, body.repo, body.role, org_id=target_org_id)
    return DashboardUserOut(login=body.login, display_name=body.display_name)


@router.delete("/admin/users/{login}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(login: str, request: Request, user: CurrentUser) -> None:
    """Borra la cuenta local y, en cascada, todos sus roles asignados
    (`database.delete_user`). Dos guardas contra dejar una organización sin
    forma de gestionarse: no se puede borrar la propia cuenta desde aquí
    (evita un auto-bloqueo accidental), ni la del único
    `admin_organizacion` que quede en alguna de sus organizaciones."""
    # Auditoría: `dashboard_users` es una tabla de INSTANCIA completa (sin
    # columna de organización, ver list_all_users) -- borrar una cuenta
    # local es una acción de superadmin de sitio, no de admin_organizacion
    # (que tras acotarlo por org no tiene autoridad verificable sobre
    # cuentas de otras organizaciones).
    if not is_site_superadmin(user.login):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Se requiere superadmin de sitio"
        )
    with database.db_session() as conn:
        if normalize_login(login) == normalize_login(user.login):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No puedes eliminar tu propia cuenta",
            )
        if database.is_last_org_admin(conn, login):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se puede eliminar al único admin_organizacion restante",
            )
        if not database.delete_user(conn, login):
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
