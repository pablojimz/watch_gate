# Plan de Implementación: Monitorización de Repositorios Externos (Rediseñado)

Este documento detalla el plan para extender la funcionalidad de WatchGate, permitiendo su uso tanto como SaaS (analizando repositorios gestionados vía eventos de la plataforma) como Herramienta de Auditoría Externa Integrada (analizando Pull Requests de terceros sin permisos de administración, visualizado directamente en el dashboard) y mediante scripts.

## Fase 1: Modelo de Datos Extensible y Seguro
Desacoplar las integraciones VCS de la Organización para permitir múltiples tokens y proveedores (GitHub, GitLab, etc.) en un futuro.
- **Nuevo Modelo `VCSConnection`**: Crear tabla para almacenar conexiones a proveedores (ej. `github`), referenciada a `Organization`.
  - Campos clave: `provider`, `installation_id`, `access_token` (cifrado).
- **Cifrado de Secretos**: Implementar cifrado simétrico (ej. Fernet) en la capa de persistencia para el campo `access_token` de `VCSConnection` para prevenir exposición en texto plano. Usar la misma infraestructura de cifrado prevista para `custom_llm_api_key`.
- **Nuevo Modelo `MonitoredRepo`**: Crear una tabla vinculada a `VCSConnection` y `Organization` que guarde:
  - Ruta del repositorio (`owner/repo`).
  - Tipo de monitorización (`managed` para webhooks, `audited` para solo lectura externa).
  - Estado y última vez escaneado.

## Fase 2: Cliente VCS Resiliente y Extracción de Diffs
- **Refactorizar `GitHubClient`**: Moverlo a `watchgate/adapters/github_client.py` para uso global.
- **Manejo de Rate Limits**: Implementar lógica de *backoff* y respeto a las cabeceras `X-RateLimit-Reset` de GitHub para evitar bloqueos por HTTP 429.
- **Descarga Conjunta (Diff + Metadata) y Límites**: 
  - Limitar la descarga de Diffs a un máximo de **2MB** para prevenir bloqueos por OOM (Out Of Memory).
  - `get_pull_request_diff`: Obtener el parche como texto plano (`Accept: application/vnd.github.v3.diff`).
  - Obtener el JSON de la PR simultáneamente para recuperar la información del autor (necesario para la Capa de Reputación al no tener `.git` local).

## Fase 3: Orquestación Asíncrona (Colas y Workers)
Reemplazar el uso de `BackgroundTasks` de FastAPI por un sistema robusto y dedicado.
- **Tecnología de Cola**: Se utilizará **RQ (Redis Queue)** para la encolación de tareas en el entorno de despliegue principal. Para entornos locales/testing se podrá usar modo síncrono.
- **Worker Independiente**: Desplegar un proceso `worker` en background separado de FastAPI para procesar el pipeline del LLM/RAG.
- **Actualización Atómica de Cuota**: Asegurar que el descuento de cuota en `UserTokenUsage` se realice atómicamente a nivel base de datos (`UPDATE ... SET tokens_used = tokens_used + X`) para prevenir condiciones de carrera entre workers.

## Fase 4: API, UI y Webhooks Seguros
- **Validación de Webhooks**: Implementar obligatoriamente la validación criptográfica (`X-Hub-Signature-256`) en los endpoints que reciban eventos de GitHub (`managed`).
- **Dashboard UI & API**: Crear sección "Repositorios Externos" y "Auditoría".
- **Reducción de Scope (Auditoría Bajo Demanda)**: Para evitar cargas masivas, el Dashboard no permitirá auditar N PRs de un repositorio de terceros en bloque. La funcionalidad de auditoría en la UI pedirá la URL de **una Pull Request concreta** a auditar, limitando el procesamiento a 1 PR por invocación. Los resultados se guardarán en `pr_scores`.

## Fase 5: Soporte para Escaneo Masivo Externo (Script CLI)
Para los usuarios que deseen auditar decenas de PRs a la vez, se puede crear un script CLI independiente que interactúe iterativamente con la API pública de GitHub y emita los resultados vía `watchgate analyze --diff-stdin`. Esto delega la gestión de rate-limits y concurrencia masiva al cliente, protegiendo los recursos del SaaS.

*Nota: Se ha proporcionado un script de ejemplo (`audit_external_repos.sh`) como caso de uso externo al repositorio principal.*

## Asignación
Esta implementación queda asignada a **Pablo Ayllón García** (Línea 1 - Núcleo, Orquestador y Engine API SaaS).