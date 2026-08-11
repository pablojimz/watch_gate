# Plan de Implementación: Monitorización de Repositorios Externos

Este documento detalla el plan para extender la funcionalidad de WatchGate, permitiendo añadir y analizar repositorios externos (como `openclaw/openclaw-server`) de forma centralizada a través del Dashboard y la recepción de webhooks, sin necesidad de clonar repositorios completos en el servidor.

## Fase 1: Extensión del Modelo de Datos (Dashboard)

El sistema necesita almacenar credenciales para acceder a repositorios externos y asociar repositorios monitorizados a organizaciones.

- **Actualizar `Organization`**: Añadir un campo `vcs_installation_id` o `vcs_access_token` en `watchgate/db/models.py`.
- **Nuevo Modelo `MonitoredRepo`**: Crear una tabla vinculada a `Organization` que guarde la ruta del repositorio (`owner/repo`) y el estado de la monitorización.

## Fase 2: Interfaz de Usuario y API del Dashboard

Permitir a los usuarios del dashboard añadir y gestionar repositorios monitorizados.

- **Endpoints REST**: Crear `POST /api/v1/repos/external` y `GET /api/v1/repos/external` en el backend del dashboard (idealmente un router nuevo `repos.py`).
- **Dashboard UI**: Añadir sección "Monitorizar Repo" en el frontend para ingresar la URL/ruta (`owner/repo`) de forma amigable.

## Fase 3: Extracción de Diffs sin Clonar

Para analizar código externo de manera eficiente y escalable desde el Engine API Server SaaS, se debe descargar únicamente el diff en texto plano.

- **Refactorizar `GitHubClient`**: Mover `github_client.py` de `adapters/github_action/` a `watchgate/adapters/github_client.py` para usarlo globalmente.
- **Nuevo método `get_pull_request_diff`**: Implementar en `GitHubClient` una llamada a la API (`Accept: application/vnd.github.v3.diff`) para obtener el parche, y utilizar `parse_diff_from_text` (ya existente en `diffparser.py`) para parsearlo sin requerir `git` local.

## Fase 4: Procesamiento Asíncrono de Webhooks

Conectar el Engine API para que cuando se abra o actualice un PR en un repo externo monitorizado, WatchGate procese el evento y asigne las cuotas correctamente.

- **FastAPI BackgroundTasks**: En `watchgate/api/routers/webhooks.py`, el webhook responderá a GitHub/GitLab con `202 Accepted` de inmediato para evitar timeouts.
- **Flujo de Análisis Asíncrono**:
  1. Obtener el diff con `GitHubClient.get_pull_request_diff`.
  2. Parsearlo a un `NormalizedDiff`.
  3. Ejecutar el pipeline llamando a `QuotaService.analyze_with_quota` para descontar el coste de la organización dueña del repo monitorizado.
  4. Formatear la salida a Markdown vía `comment_template.py`.
  5. Publicar el análisis como un comentario en el PR remoto con `GitHubClient.post_comment`.

## Asignación
Esta implementación queda asignada a **Pablo Ayllón García** (Línea 1 - Núcleo, Orquestador y Engine API SaaS).