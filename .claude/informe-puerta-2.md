# Auditoría: escaneo de PRs disparado desde el dashboard

Ámbito: repos "conectados manualmente" (`MonitoredRepo`, tipos `audited`/`managed`) +
botón de escaneo, y el webhook de GitHub que dispara el mismo flujo para repos `managed`.
Solo diagnóstico, sin cambios de código.

## 1. Cableado end-to-end (con evidencia)

Camino confirmado, cada salto verificado en código real (no supuesto):

- **Frontend**: `ExternalReposPage.tsx:66,79,91` → `api.scanExternalRepo` /
  `api.scanMainBranch` (`client.ts:333-342`) → `POST /repos/external/{id}/scan` o
  `/scan-main`.
- **Backend router**: `repos.py:224-247` (`scan_audited_repo`) — si hay `pr_number`,
  `queue.enqueue(run_audit_scan, ...)` (línea 226-233); si no, delega en
  `RepoPollingService.poll_repo_by_id` (línea 242), que lista PRs abiertas vía
  `GitHubClient.list_all_open_pull_requests` y encola `run_audit_scan` por cada una
  (`repo_polling.py:153-176`). `scan_main_branch` (`repos.py:250-284`) encola
  `run_main_branch_scan` vía `_enqueue_main_branch_scan` (línea 55-101).
- **Worker (RQ)**: `tasks.py` — `run_audit_scan` (233-325), `run_main_branch_scan`
  (132-230) y `run_managed_scan` (20-111, disparado por `webhooks.py:73-80`) siguen
  el mismo patrón: `GitHubClient.get_pull_request_data`/`get_default_branch_scan_data`
  → `parse_diff_from_text` → `QuotaService.analyze_with_quota` (`quota.py:54...`) →
  **dos escrituras separadas**, confirmadas ambas leyendo el código, no solo el
  comentario del compose:
  - `analyze_with_quota` llama a `save_pr_score` (`quota.py:181` →
    `watchgate/db/repository.py:360-380`), que escribe en la tabla `pr_scores` del
    **esquema SQLModel principal** (`watchgate/db/models.py:156-172`, `PRScore`).
  - Justo después, cada tarea llama a `insert_aggregated` (`db.py:276-338`), que
    escribe en `DashboardPRScore`, tabla `pr_scores` de la **base separada del
    Dashboard** (`watchgate_dashboard`, ver comentario explícito en
    `docker-compose.yml:79-81`: "ambos esquemas definen una tabla `pr_scores`
    incompatible entre sí"). Es el registro que de verdad lee la UI.
  - Al final, `repo_obj.last_scanned_at = datetime.now(UTC)` + `session.commit()`
    (p. ej. `tasks.py:314-325`).

**Conclusión**: el cableado es real y completo, no aspiracional — confirmado también
en caliente: en los logs del worker (`docker logs watch_gate-dashboard-worker-1`) hay
un job real `run_main_branch_scan(...)` que terminó con `Job OK` en producción local.

## 2. Manejo de errores en `run_audit_scan`/`run_managed_scan`/`run_main_branch_scan`

**Esto es lo más grave del flujo.** Las tres funciones de `tasks.py` **no tienen
ningún `try/except` alrededor del cuerpo principal** (llamada a GitHub, parseo,
análisis, inserción). El único `try/except` presente envuelve la llamada opcional a
`get_reputation_metadata` y la traga en silencio (`except Exception: pass`,
`tasks.py:177-185` y `267-274`) — un fallo ahí no rompe el escaneo, pero tampoco dice
nada a nadie.

Si `client.get_pull_request_data` lanza (token inválido, PR inexistente, fallo de red)
o `analyze_with_quota` lanza, la excepción **se propaga sin capturar** fuera de la
función de tarea. Consecuencias concretas:

- `session.commit()` final nunca se ejecuta → `last_scanned_at` **no se actualiza**.
- No hay ningún código que toque `MonitoredRepo.status` ni `consecutive_errors` desde
  estas tres funciones (confirmado por grep, ver punto 3) → el repo se queda
  exactamente como estaba, sin ningún rastro de que ese escaneo falló.
- RQ captura la excepción a su nivel (comportamiento por defecto de la librería): el
  job pasa a `FailedJobRegistry` y la traza queda en el log del proceso
  `dashboard-worker` (confirmado viendo `docker logs`). Es decir, **sí queda
  registrado, pero solo en el log de infraestructura del worker** — no hay ningún
  logger de aplicación (`logging.getLogger("watchgate...")`) que lo capture, y nada lo
  vuelca a una tabla ni a un canal visible desde el Dashboard.
- Para el usuario: **desaparece en silencio**. Ver punto 4.

Contraste: la única ruta que sí maneja fallos de forma visible es
`RepoPollingService._poll_single_candidate` (usada por "Escanear todas las PRs
abiertas" y por el alta de un repo), que envuelve **solo** la llamada a
`list_all_open_pull_requests` en `try/except` (`repo_polling.py:119-124`) y por eso
actualiza `consecutive_errors`/`status` — pero eso cubre exclusivamente el fallo al
*listar* PRs, no el fallo del *análisis* de cada PR individual, que se encola después
sin ningún seguimiento de resultado.

## 3. Campo `MonitoredRepo.status`: ¿vivo o muerto?

Grep de todas las asignaciones a `.status` sobre un `MonitoredRepo` en todo el repo:

```
watchgate/service/repo_polling.py:89   repo_db.status = "error"
watchgate/dashboard/backend/routers/repos.py:314   repo.status = data.status
```

Solo dos sitios escriben:

1. `repo_polling.py:89`, dentro de `_record_poll_outcome` — se pone a `"error"` tras 5
   fallos **consecutivos al listar PRs abiertas** (no al analizarlas). Solo se llama
   desde `_poll_single_candidate`, es decir, solo desde "Escanear todas las PRs
   abiertas" y desde el poll único al conectar un repo nuevo.
2. `repos.py:314`, en el `PATCH /repos/external/{id}` (`update_external_repo`) — acción
   manual de un admin/mantenedor (RBAC vía `require_role`), no algo que el sistema
   ponga solo.

**No está muerto**, pero está **parcialmente vivo**: se actualiza de verdad para un
subconjunto concreto de fallos (listar PRs), y el frontend sí lo pinta
(`ExternalReposPage.tsx:190-194`, badge "Error en peticiones (N fallos)"). Pero el
fallo del escaneo en sí (`run_audit_scan`/`run_main_branch_scan`/`run_managed_scan`,
que es la parte que realmente hace el trabajo) nunca toca este campo — ver punto 2.
Un repo puede fallar sistemáticamente al *analizar* cada PR y seguir mostrando
`status: "active"` sin ningún fallo acumulado.

## 4. Feedback al usuario tras encolar un escaneo

`ExternalReposPage.tsx` — revisados los tres handlers (`handleScanPr:55-74`,
`handleScanAllOpen:76-86`, `handleScanMainBranch:88-98`): cada uno hace `await
api.scan...()`, muestra un `toast.success`/`toast.error` **solo del resultado del
POST de encolado** (HTTP 202, no del resultado del análisis) y termina ahí. No llaman
a `fetchRepos()` de nuevo.

`fetchRepos()` (línea 28-36) **solo** se invoca:
- una vez al montar el componente (`useEffect`, línea 24-26), y
- después de `handleAddRepo` (línea 47).

No hay `setInterval`, `useSWR`/polling, ni WebSocket en todo el fichero (confirmado,
no hay ninguna otra ocurrencia de esos patrones). **El usuario se queda sin ninguna
señal tras el toast inicial de "encolado"**: para ver si el escaneo terminó (bien o
mal) tiene que recargar la página a mano — momento en el que, si falló silenciosamente
(punto 2), tampoco verá nada distinto salvo que sea uno de los fallos de listado que sí
tocan `status`/`consecutive_errors` (punto 3).

## 5. Estado real de la infraestructura

Comprobado con `docker compose ps` (stack ya levantado):

```
watch_gate-redis-1                redis:7-alpine       Up 3 días (healthy)
watch_gate-dashboard-worker-1     rq worker --url redis://...   Up ~1h
watch_gate-dashboard-backend-1    uvicorn ...           Up ~1h (healthy)
watch_gate-postgres-1             postgres:16-alpine    Up 3 días (healthy)
```

Redis accesible y sano. Hay un proceso `dashboard-worker` real consumiendo la cola
(`rq worker`) — confirmado no solo por estar "Up", sino leyendo su log
(`docker logs watch_gate-dashboard-worker-1`): arrancó, recogió un job
`run_main_branch_scan(...)` a las 10:10:43 y lo terminó con `Job OK` a las 10:11:28.
**No hay jobs quedándose encolados sin procesar** — la infraestructura funciona.

## 6. Cobertura de tests

Tests localizados que tocan este flujo: `tests/unit/test_repos_scan.py` (24 tests),
`tests/unit/test_dashboard_github_webhook.py` (4 tests), `tests/unit/test_github_client.py`
(14 tests). Ejecutados dentro del contenedor `dashboard-backend` (pytest no está en el
entorno local ni en la imagen; se instaló solo temporalmente ahí para poder correrlos,
sin tocar código):

```
36 passed, 1 warning in 4.16s
```

**Todo pasa.** Pero la cobertura tiene un hueco claro:

- **No existe ningún `tests/unit/test_tasks.py`** (ni equivalente). `run_audit_scan`,
  `run_managed_scan` y `run_main_branch_scan` — las tres funciones que de verdad
  ejecutan el análisis — **no tienen ni un solo test directo**, ni de camino feliz ni
  de fallo.
- El único test que cubre un camino de error es
  `test_poll_repo_by_id_enqueues_and_handles_repeated_errors`
  (`test_repos_scan.py:114-156`) y `test_poll_repo_by_id_malformed_repo_path_does_not_raise`
  (línea 159-188) — ambos prueban el fallo de **listar** PRs
  (`RepoPollingService`), no el fallo del **análisis** de una PR concreta.
  Consistente con el punto 2: como el código de producción no maneja ese fallo,
  tampoco hay ningún test que lo ejercite.
- Los tests de `repos.py` cubren bien el encolado feliz y la deduplicación de jobs
  (`test_add_external_repo_*`, `test_scan_main_branch_endpoint_*`), pero ninguno
  simula que `run_audit_scan` lance una excepción para comprobar qué pasa después.

## Resumen (de más a menos grave)

- 🔴 **Roto / sin implementar**: si el análisis en sí falla (`run_audit_scan`,
  `run_managed_scan`, `run_main_branch_scan` — token inválido, PR borrada, fallo de
  red con GitHub, excepción del pipeline de análisis), no se captura, no se refleja en
  `status`/`consecutive_errors`, no se loguea a nivel de aplicación y el usuario no se
  entera de ninguna forma salvo mirar los logs crudos de `dashboard-worker`. Es el
  hueco más serio de todo el flujo, y no tiene ni un test que lo cubra.
- 🟠 **A medias**: `MonitoredRepo.status` sí se actualiza automáticamente, pero solo
  para el fallo de *listar* PRs abiertas (`RepoPollingService`), no para el fallo de
  *analizarlas* — da una falsa sensación de que el campo cubre todos los fallos cuando
  cubre solo uno.
- 🟠 **A medias**: feedback al usuario tras encolar — hay toast de "encolado" pero cero
  señal posterior (sin polling/refresco/websocket); hay que recargar a mano, y aun
  recargando, un fallo de análisis puro no deja ningún rastro visible (ver punto
  anterior).
- 🟡 **A medias**: cobertura de tests — sólida para el cableado de encolado (36/36
  pasan), pero con un vacío total sobre el comportamiento de fallo del análisis real
  (`tasks.py`), justo la pieza más frágil.
- 🟢 **Funciona de verdad**: el cableado end-to-end en el camino feliz (frontend →
  endpoint → cola RQ → worker → `QuotaService` → doble escritura en `pr_scores`
  (esquema principal) y `pr_scores`/`DashboardPRScore` (esquema dashboard, el que lee
  la UI) → `last_scanned_at`), confirmado con evidencia de línea y con un job real
  visto terminar en logs del worker. Infraestructura (Redis + worker) sana y
  consumiendo la cola sin atascos.
