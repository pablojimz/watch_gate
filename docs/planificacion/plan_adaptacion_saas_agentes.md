# Plan Maestro de Adaptación SaaS, Agentes e Infraestructura Git Multi-Plataforma

**Documento de Planificación Técnica y Arquitectura Unificada**
**Fecha**: Agosto 2026
**Estado**: Aprobado tras Auditoría Crítica Completa (Fase 1 Completada, Fase 2 en Desarrollo)
**Ubicación**: `docs/planificacion/plan_adaptacion_saas_agentes.md`

---

## 1. Resumen Ejecutivo y Objetivos

El objetivo de este plan maestro es evolucionar **WatchGate** desde un motor de análisis de riesgo de Pull Requests orientado a CI/CD y usuarios individuales hacia una **plataforma SaaS Multi-Tenant nativa para Agentes de IA e infraestructura Git Multi-Plataforma** (GitHub, GitLab, Bitbucket, Azure DevOps, Gitea, Gitolite y servidores Git Bare corporativos).

### Objetivos Clave
1. **Soporte de Protocolo MCP (Model Context Protocol)**: Ofrecer integración nativa mediante el servidor MCP en modo `stdio` para Agentes de IA locales e IDEs (OpenCode, Cursor, VS Code, Claude Desktop).
2. **API REST Nativa para Agentes SaaS**: Proporcionar endpoints REST (`/api/v1/agent/*`) optimizados para agentes remotos en la nube (Devin, Copilot Workspace, runners distribuidos).
3. **Soporte Git Multi-Plataforma e Intercepción `pre-receive`**:
   * Adaptador de Hook servidor POSIX `pre-receive` (`watchgate/adapters/git_hook/pre_receive.py`) con manejo explícito de SHA nulo (`00*40`) y timeout HTTP restringido (<8s) para interceptar `git push` en servidores Git corporativos (GitLab Self-Managed, Bitbucket Data Center, Gitolite, Gerrit, repos Bare SSH) antes de fusionar código a producción.
   * Receiver de Webhooks multi-proveedor en `watchgate/api/routers/webhooks.py` con verificadores de firma HMAC independientes para GitHub, GitLab y Bitbucket.
4. **Arquitectura Multi-Tenant e Identidad Ligera de Agentes**: Garantizar el aislamiento estricto de datos por Organización (`org_id`) y permitir trazabilidad por agente mediante cabeceras opcionales (`X-WatchGate-Agent-ID`, `X-WatchGate-Agent-Name`).
5. **Gobernanza Centralizada de Políticas (`PolicyService`)**: Almacenamiento simplificado mediante `policy_json` en `Organization` para asegurar la prevalencia obligatoria de las reglas de la Organización sobre el archivo local `.watchgate.yml`.
6. **Contrato de Datos Orientado a Autocorrección**: Proporcionar respuestas con estructuración accionable (`AgentGuidance`, `remediation_hints`, `actionable_steps`) para permitir bucles de autocorrección (*Agent Self-Correction*).
7. **Control de Coste con Modo Degradado Inteligente (Opción B), Inyección de Sesión y Concurrencia Atómica**: `QuotaService` con inyección de `Session` SQLModel y límites de presupuesto mensual de tokens por Organización mediante incrementos SQL atómicos. Al alcanzar el límite, el sistema conmuta automáticamente a **Modo Degradado Inteligente** (fallback determinista con HTTP 200 OK) sin romper la ejecución del agente.
8. **Preservación del Principio A.0 (Core Agnóstico)**: Mantener el núcleo `watchgate.core` libre de acoplamiento a conceptos SaaS, `org_id` o autenticación HTTP.

---

## 2. Principios de Diseño y Guardarraíles de Arquitectura en 3 Capas

Para garantizar la coexistencia limpia de los 3 modos de operación (CLI Local, CI/CD GitHub/GitLab Action, y Plataforma Enterprise SaaS / Proxy Hook), se aplica el patrón **Clean Architecture en 3 Capas Aisladas**:

```
+-----------------------------------------------------------------------------------+
|                        CAPA 1: ADAPTADORES DE ENTRADA (Input)                     |
|                                                                                   |
|  [Modo 1: Local]          [Modo 2: CI/CD]               [Modo 3: Enterprise SaaS]   |
|   - CLI (`cli.py`)         - GitHub Action               - Engine API (/api/v1/)      |
|                            - GitLab CI Runner            - Git `pre-receive` Hook     |
|                                                          - Servidor MCP (Agentes)     |
+-------------------------------------+---------------------------------------------+
                                      |
                                      v
+-----------------------------------------------------------------------------------+
|                   CAPA 2: SERVICIOS Y GOBERNANZA SAAS (watchgate/service/)        |
|                                                                                   |
|   - QuotaService (Inyección de Session + Cuotas Org + Modo Degradado B)           |
|   - PolicyService (policy_json Org sobre .watchgate.yml local)                    |
+-------------------------------------+---------------------------------------------+
                                      |
                                      v
+-----------------------------------------------------------------------------------+
|                     CAPA 3: NÚCLEO TÉCNICO PURO (watchgate.core)                  |
|                                                                                   |
|   - run_full_analysis()  - Orquestador Concurrente   - 4 Capas de Análisis         |
|   - Aggregator & Score   - Shortcircuit Determinista - Extractor de Diffs         |
+-------------------------------------+---------------------------------------------+
```

### Guardarraíles Obligatorios:
1. **Aislamiento del Core (`watchgate.core`)**:
   * `watchgate.core` permanece **100% agnóstico de plataforma y tenant**.
   * Ningún modelo en `watchgate.core.models` contendrá campos como `org_id`, `agent_id` o `tenant_quota`.
   * Los modelos específicos de agentes (`AgentGuidance`, `ActionableStep`) pertenecen exclusivamente a la capa de adaptación (`watchgate/api/schemas/agent.py` y `watchgate/mcp/schemas.py`).
2. **Capa de Servicio de Aplicación (`watchgate/service/`)**:
   * `QuotaService` acepta una `sqlmodel.Session` explícita para orquestar transacciones sin conexiones huérfanas.
   * `PolicyService` orquesta la prevalencia de reglas corporativas sobre `.watchgate.yml` mediante la columna `policy_json`.
3. **Aislamiento Multi-Tenant Estricto en Caché Semántica**:
   * La tabla `SemanticCache` utiliza una clave primaria compuesta `(org_id, diff_hash)` para impedir fugas de información o reutilización no autorizada de respuestas entre organizaciones.
4. **Ajuste de Concurrencia Atómica en Cuotas**:
   * La imputación de consumo de tokens se realiza mediante consultas SQL atómicas (`UPDATE user_token_usage SET tokens_used = tokens_used + :inc ...`) para prevenir condiciones de carrera cuando un agente emite peticiones paralelas.
5. **Fórmula Matemática de Re-normalización de Pesos en Modo Degradado**:
   * Cuando la capa semántica se omite por presupuesto (`semantic = 0`), los pesos de las capas activas restantes $k \in \{\text{static, deps, vulnerabilities, reputation}\}$ se re-normalizan mediante:
     $$w'_i = \frac{w_i}{\sum_{k \in \text{activas}} w_k}$$

---

## 3. Arquitectura de Datos Multi-Tenant (`watchgate/db/`)

Se extiende el esquema relacional en `watchgate/db/models.py`.

```
 +------------------+           +------------------+           +------------------+
 |   Organization   | 1       N |      User        | 1       N |    UserAPIKey    |
 | (policy_json)    |<----------|                  |<----------|   (Org / Agent)  |
 +------------------+           +------------------+           +------------------+
          | 1                                                           |
          |                                                             |
          v N                                                           v
 +------------------+           +------------------+           +------------------+
 | UserTokenUsage   |           |     PRScore      |           |  SemanticCache   |
 | (Monthly Quota)  |           | (Historic Audit) |           | (Tenant-Scoped)  |
 +------------------+           +------------------+           +------------------+
```

### 3.1 Estructura del Modelo `Organization`
* `id`: `str` (UUID primary key).
* `name`: `str` (Nombre de la organización).
* `plan_tier`: `str` (`"starter"`, `"pro"`, `"enterprise"`).
* `monthly_token_quota`: `int` (Cuota mensual de tokens).
* `policy_json`: `str | None` (JSON serializado con reglas y umbrales corporativos obligatorios).
* `created_at`: `datetime`.

---

## 4. Servicio de Cuotas y Gobernanza (`watchgate/service/`)

### 4.1 `QuotaService` (`watchgate/service/quota.py`)
1. Constructor / Métodos reciben una `sqlmodel.Session` activa para gestión limpia de transacciones.
2. Consulta el consumo acumulado del mes para `org_id` en `UserTokenUsage`.
3. Compara `tokens_used` contra `organization.monthly_token_quota`.
4. **Si `tokens_used >= monthly_token_quota`**:
   * Activa el **Modo Degradado Inteligente**.
   * Omite la capa semántica (`semantic.skipped = True`, `skip_reason = "Cuota mensual de tokens alcanzada. Modo Degradado Determinista activo."`).
   * Ejecuta capas deterministas (**Estática**, **Dependencias**, **Vulnerabilidades**, **Reputación**).
   * Re-normaliza los pesos de las capas activas según la fórmula $w'_i = \frac{w_i}{\sum w_k}$.
   * Retorna `HTTP 200 OK` con aviso explícito.
5. **Imputación Atómica**: Incremento de tokens post-análisis vía SQL atómico `UPDATE user_token_usage SET tokens_used = tokens_used + :inc WHERE org_id = :org_id AND month = :month`.

### 4.2 `PolicyService` (`watchgate/service/policy.py`)
1. Lee `organization.policy_json` si está presente.
2. Aplica overrides sobre la instancia `WatchGateConfig` producida por `.watchgate.yml`.
3. Registra en los logs el origen de cada umbral o peso modificado para facilitar la auditoría.

---

## 5. Endpoints REST y Esquemas de Adaptación (`watchgate/api/routers/agent.py`)

Añadir el router dedicado `/api/v1/agent` dentro de `watchgate/api/`.

### 5.1 Rutas REST
1. **`POST /api/v1/agent/precheck`**:
   * Ejecuta solo las capas deterministas (`static`, `dependencies`, `vulnerabilities`). Respuesta < 100 ms. Cero consumo LLM.
2. **`POST /api/v1/agent/analyze`**:
   * Ejecuta el pipeline de análisis mediante `QuotaService`. Retorna `AggregatedResult` mapeado junto con `AgentGuidance`.
3. **`POST /api/v1/agent/verify-fix`**:
   * Recibe el parche previo (`original_diff`) y el nuevo parche candidato (`candidate_diff`).
   * **Algoritmo de Matching**: Compara firmas de hallazgos basadas en `rule_id` + `file_path` + `code_hunk_hash` (en lugar de líneas absolutas) para determinar cuáles hallazgos fueron efectivamente resueltos.
   * Retorna delta de riesgo (`risk_reduced: bool`, `resolved_findings`, `remaining_findings`).
4. **`GET /api/v1/agent/policy`**:
   * Devuelve las políticas de la organización (umbrales, reglas activas y cuota de tokens restante).

---

## 6. Adaptadores Multi-Plataforma Git (`watchgate/adapters/` & Webhooks)

1. **Hook POSIX `pre-receive` Universal (`watchgate/adapters/git_hook/pre_receive.py`)**:
   * Lee `<old-sha> <new-sha> <refname>` desde `stdin`.
   * **Manejo de SHA Nulo**: Si `old-sha` es `00*40` (push inicial o creación de rama/tag), utiliza `git diff-tree` para extraer los cambios del commit sin fallar.
   * **Timeout HTTP Restringido**: Aplica un timeout estricto de 8 segundos en la petición a la Engine API. Si expira, aplica política de contingencia (bloqueo `fail_closed` por defecto en enterprise).
   * Si el semáforo es **ROJO** y `block_on_red` está activo, retorna `exit 1` y bloquea el `git push` imprimiendo la justificación de seguridad por `stderr`.
2. **Webhooks Multi-Proveedor (`watchgate/api/routers/webhooks.py`)**:
   * Routers para **GitHub** (`/webhooks/github`), **GitLab** (`/webhooks/gitlab`) y **Bitbucket** (`/webhooks/bitbucket`).
   * Verificadores de firma independientes por proveedor (`X-Hub-Signature-256`, `X-Gitlab-Token`, `X-Hub-Signature`).

---

## 7. Servidor MCP Nativo en `stdio` (`watchgate/mcp/`)

Módulo `watchgate/mcp/` habilitando el estándar **Model Context Protocol** como un adaptador fino sobre la capa de servicios de aplicación con 5 herramientas: `watchgate_analyze_diff`, `watchgate_precheck`, `watchgate_explain_risk`, `watchgate_verify_fix`, `watchgate_query_threat_kb`.

---

## 8. Plan de Implementación Recomendado Fase a Fase

| Fase | Descripción y Objetivos | Estado |
|---|---|---|
| **Fase 1** | **Capa de Datos Multi-Tenant & Autenticación**: `Organization`, `org_id`, `agent_id`, `SemanticCache` aislada e imputación de tokens. | **COMPLETADO** |
| **Fase 2** | **Capa de Servicios de Gobernanza y Cuotas (`watchgate/service/`)**: `QuotaService` (con inyección de Session, control de presupuesto + Modo Degradado B con HTTP 200 OK) y `PolicyService` (con `policy_json`). | **EN DESARROLLO (Siguiente)** |
| **Fase 3** | **Adaptadores REST para Agentes de IA (`watchgate/api/routers/agent.py`)**: `/precheck`, `/analyze`, `/verify-fix` con matching sintáctico y `AgentGuidance`. | **PENDIENTE** |
| **Fase 4** | **Adaptadores Multi-Plataforma Git & Webhooks**: Hook `pre-receive` universal con timeout <8s y manejo de SHA nulo (`watchgate/adapters/git_hook/`), y Webhooks para GitLab/Bitbucket. | **PENDIENTE** |
| **Fase 5** | **Servidor MCP Nativo (`watchgate/mcp/`)**: Servidor MCP en modo `stdio` con las 5 herramientas de seguridad. | **PENDIENTE** |
| **Fase 6** | **Métricas en Dashboard & Manuales Multi-Git**: Panel de control SaaS y manuales `docs/manual_mcp.md` y `docs/manual_git_hooks.md`. | **PENDIENTE** |

---

## 9. Criterios de Aceptación y Verificación

1. **Aislamiento Multi-Tenant**: Confirmar que la Organización A no puede leer ni reutilizar análisis o cachés de la Organización B.
2. **Concurrencia de Tokens**: Validar con peticiones simultáneas que la suma de `tokens_used` en BD es exacta.
3. **Modo Degradado**: Comprobar que al superar la cuota el análisis devuelve HTTP 200 OK con capas deterministas, re-normalización de pesos y `semantic.skipped = True`.
4. **Hook `pre-receive` Robusto**: Probar intercepción de `git push` con manejo de SHA nulo `00*40`, timeout HTTP de 8s y rechazo en terminal cuando el semáforo es ROJO.
5. **Servidor MCP (`stdio`)**: Invocación exitosa de herramientas MCP vía `stdio`.
6. **Preservación del Core**: Verificar que `watchgate.core` no contiene dependencias hacia `watchgate.api` ni `watchgate.db`.
7. **Calidad de Código**: `pytest`, `ruff check .` y `mypy watchgate` ejecutados sin errores.
