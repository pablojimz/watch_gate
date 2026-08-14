Conecta la Puerta 3 (POST /api/v1/analyze, watchgate/api/routers/analyze.py)
con la base de datos del dashboard (watchgate/dashboard/backend/db.py), para
que un análisis que entra por ahí aparezca en la pantalla /repos del
frontend (ReposPage.tsx).

Contexto que necesitas saber (verifícalo tú mismo antes de tocar nada):
- watchgate/dashboard/backend/db.py tiene 3 tablas relevantes:
  - pr_scores: el histórico real de análisis. Hay que escribir aquí SIEMPRE.
  - repo_roles: quién puede VER cada repo en el dashboard. Un usuario no-admin
    solo ve en /repos los repos donde tiene fila aquí (ver
    list_repos_for_user en el mismo fichero). Hay que escribir aquí también,
    si no el resultado queda invisible para usuarios no-admin.
  - repo_settings: pesos/umbrales personalizados por repo. NO hace falta
    tocarla -- si no existe fila, el dashboard usa los valores por defecto
    de la organización. No la toques en este cambio.
- Las funciones ya existentes que necesitas (NO las reimplementes):
  - insert_aggregated(conn, result, author_login=...) -- escribe en pr_scores.
  - upsert_role(conn, user_login, repo, role) -- escribe en repo_roles.
  - db_session() -- context manager de conexión a esta base de datos.
  Las tres están en watchgate/dashboard/backend/db.py. Mira cómo las usa
  watchgate/dashboard/backend/tasks.py (run_managed_scan / run_audit_scan)
  como referencia exacta del patrón a seguir -- es literalmente el mismo
  problema ya resuelto ahí, solo que para la Puerta 2, no la 3.
- analyze_pr() en analyze.py ya recibe `auth: tuple[UserAPIKey, User, Organization]`
  vía Depends(require_scope(...)) -- el `User` de ahí (watchgate/db/models.py)
  tiene un campo `.name` que YA es el login normalizado que usa el sistema de
  sesiones del dashboard (así lo crea _get_or_create_db_user en
  dashboard/backend/routers/keys.py: create_user(session, email=..., name=normalized)).
  Úsalo directamente para upsert_role, no hace falta volver a resolverlo
  como hace tasks.py.

Plan:

1. En analyze_pr(), justo después de obtener `result` de
   quota_service.analyze_with_quota(...) y ANTES del `return result`, añade:

   from watchgate.dashboard.backend.db import db_session as dashboard_db_session
   from watchgate.dashboard.backend.db import insert_aggregated, upsert_role

   author_login = request.metadata.get("author_login") or (
       request.authors[0].login if request.authors else None
   )
   try:
       with dashboard_db_session() as dash_conn:
           insert_aggregated(dash_conn, result, author_login=author_login)
           upsert_role(dash_conn, user.name, result.repo, "admin_organizacion")
   except Exception:
       logger.warning(
           "No se pudo persistir el resultado en el dashboard para repo=%s pr_id=%s",
           result.repo, result.pr_id, exc_info=True,
       )

   Es IMPORTANTE que sea best-effort (try/except que solo loguea, nunca
   relanza): si esto falla, la petición HTTP igualmente debe devolver 200
   con el resultado del análisis -- ese análisis ya se hizo y ya se guardó
   en la base de datos A (PRScore vía save_pr_score), perder solo el espejo
   en el dashboard es degradado, no crítico. Sigue el mismo criterio que ya
   documenta watchgate/adapters/github_action/dashboard_client.py para el
   mismo tipo de fallo.

2. Añade un logger si el fichero no tiene uno ya (`logger = logging.getLogger(__name__)`).

3. Test en tests/unit/ (busca los tests existentes de analyze.py y sigue su
   estilo): que una llamada exitosa a /api/v1/analyze efectivamente deja una
   fila nueva en pr_scores (base de datos del dashboard) y una fila en
   repo_roles para el usuario de la API key, con role="admin_organizacion".
   Añade también un test de que si dashboard_db_session() lanza una
   excepción (mockéala), /api/v1/analyze sigue devolviendo 200 con el
   resultado igualmente -- no debe propagar el fallo al cliente.

4. NO toques watchgate/config.py ni watchgate/dashboard/backend/db.py para
   "unificar" los DEFAULT_WEIGHTS que difieren entre ambos (semantic 0.40
   vs 0.35, dependencies 0.10 vs 0.15) -- es una decisión de producto
   aparte, solo déjalo anotado en tu resumen final como algo pendiente de
   decidir, no lo toques en este cambio.

5. Corre pytest al final y pega en tu resumen la salida concreta de los
   tests nuevos (PASSED/FAILED), no un "todo verde" genérico.

