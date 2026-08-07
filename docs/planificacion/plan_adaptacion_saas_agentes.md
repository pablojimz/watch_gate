# Plan de Adaptación de WatchGate para Entornos SaaS y Agentes de IA

**Documento de Planificación Técnica y Arquitectura**
**Fecha**: Agosto 2026
**Estado**: Aprobado tras Auditoría Crítica de Arquitectura (Segunda Revisión Completa)
**Ubicación**: `docs/planificacion/plan_adaptacion_saas_agentes.md`

---

## 1. Resumen Ejecutivo y Objetivos

El objetivo de este plan es evolucionar **WatchGate** desde un motor de análisis de riesgo de Pull Requests orientado a CI/CD y usuarios individuales hacia una **plataforma SaaS Multi-Tenant nativa para Agentes de Inteligencia Artificial** (coding agents, sistemas autónomos de remediación y asistentes de IDE).

### Objetivos Clave
1. **Soporte de Protocolo MCP (Model Context Protocol)**: Ofrecer integración nativa mediante el servidor MCP en modo `stdio` para Agentes de IA locales e IDEs (OpenCode, Cursor, VS Code, Claude Desktop).
2. **API REST Nativa para Agentes SaaS**: Proporcionar endpoints REST (`/api/v1/agent/*`) optimizados para agentes remotos en la nube (Devin, Copilot Workspace, runners distribuidos).
3. **Arquitectura Multi-Tenant e Identidad Ligera de Agentes**: Garantizar el aislamiento estricto de datos por Organización (`org_id`) y permitir trazabilidad por agente mediante cabeceras opcionales (`X-WatchGate-Agent-ID`, `X-WatchGate-Agent-Name`).
4. **Contrato de Datos Orientado a Autocorrección**: Proporcionar respuestas con estructuración accionable (`AgentGuidance`, `remediation_hints`, `actionable_steps`) en la capa de adaptación de la API para permitir bucles de autocorrección (*Agent Self-Correction*).
5. **Endpoint de Pre-check Ultrarrápido**: Permitir evaluaciones ligeras en milisegundos (capas estática + dependencias) sin costo de inferencia LLM.
6. **Control de Coste con Modo Degradado Inteligente (Opción B) y Concurrencia Atómica**: Aplicar límites de presupuesto mensual de tokens por Organización mediante incrementos SQL atómicos. Al alcanzar el límite, el sistema conmuta automáticamente a **Modo Degradado Inteligente** (fallback determinista con HTTP 200 OK) sin romper la ejecución del agente.
7. **Preservación del Principio A.0 (Core Agnóstico)**: Mantener el núcleo `watchgate.core` libre de acoplamiento a conceptos SaaS, `org_id` o autenticación HTTP.

---

## 2. Principios de Diseño y Guardarraíles de Arquitectura

Para garantizar robustez, mantenibilidad y rendimiento en producción SaaS multi-nodo, se establecen los siguientes guardarraíles de diseño obligatorios:

1. **Aislamiento del Core (`watchgate.core`)**:
   * `watchgate.core` permanece **100% agnóstico de plataforma y tenant**.
   * Ningún modelo en `watchgate.core.models` contendrá campos como `org_id`, `agent_id` o `tenant_quota`.
   * Los modelos específicos de agentes (`AgentGuidance`, `ActionableStep`) pertenecen exclusivamente a la capa de adaptación (`watchgate/api/schemas/agent.py` y `watchgate/mcp/schemas.py`).
2. **Capa de Servicio de Aplicación (`watchgate/service/`)**:
   * Se introduce una capa intermedia de servicios (`QuotaService`, `AgentAnalysisService`) que orquesta la verificación de cuotas, invoca el Core pipeline y genera la respuesta enriquecida.
3. **Aislamiento Multi-Tenant Estricto en Caché Semántica**:
   * La tabla `SemanticCache` utilizará una clave primaria compuesta `(org_id, diff_hash)` para impedir fugas de información o reutilización no autorizada de respuestas entre organizaciones.
4. **Persistencia SaaS Preparada para Multi-Nodo**:
   * Las operaciones de base de datos se unifican sobre SQLModel/PostgreSQL (`watchgate/db/`), eliminando la dependencia exclusiva de archivos SQLite locales (`.watchgate/cost.db`) en producción.
5. **Ajuste de Concurrencia Atómica en Cuotas**:
   * La imputación de consumo de tokens se realizará mediante consultas SQL atómicas (`UPDATE user_token_usage SET tokens_used = tokens_used + :inc ...`) para prevenir condiciones de carrera cuando un agente emite peticiones paralelas.
6. **Fórmula Matemática de Re-normalización de Pesos en Modo Degradado**:
   * Cuando la capa semántica se omite por presupuesto (`semantic = 0`), los pesos de las capas activas restantes $k \in \{\text{static, deps, reputation}\}$ se re-normalizan mediante:
     $$w'_i = \frac{w_i}{\sum_{k \in \text{activas}} w_k}$$
7. **Simplificación del Alcance MCP (V1 en `stdio`)**:
   * El Servidor MCP operará en modo **`stdio`** (estándar de integración para IDEs locales). Para la comunicación remota en la nube se utilizará la API REST nativa, posponiendo el transporte SSE para evitar sobreingeniería de estado de sesión.

---

## 3. Arquitectura de Datos Multi-Tenant (`watchgate/db/`)

Se extiende el esquema relacional en `watchgate/db/models.py`.

```
 +------------------+           +------------------+           +------------------+
 |   Organization   | 1       N |      User        | 1       N |    UserAPIKey    |
 |    (Tenant)      |<----------|                  |<----------|   (Org / Agent)  |
 +------------------+           +------------------+           +------------------+
          | 1                                                           |
          |                                                             |
          v N                                                           v
 +------------------+           +------------------+           +------------------+
 | UserTokenUsage   |           |     PRScore      |           |  SemanticCache   |
 | (Monthly Quota)  |           | (Historic Audit) |           | (Tenant-Scoped)  |
 +------------------+           +------------------+           +------------------+
```

### 3.1 Modificaciones en el Esquema SQLModel (`watchgate/db/models.py`)

1. **`Organization` (Nuevo)**:
   * `id`: `str` (UUID primary key).
   * `name`: `str` (Nombre de la empresa u organización).
   * `plan_tier`: `str` (ej. `"starter"`, `"pro"`, `"enterprise"`).
   * `monthly_token_quota`: `int` (Límite mensual de tokens LLM, ej. 1,000,000).
   * `created_at`: `datetime`.

2. **Actualización en `User`**:
   * Añadir `org_id`: `str | None` (FK opcional a `organizations.id`).

3. **Actualización en `UserAPIKey`**:
   * Añadir `org_id`: `str | None` (Indexado para filtrado multi-tenant).
   * Añadir `default_agent_name`: `str | None` (Nombre descriptivo opcional del agente).

4. **Actualización en `UserTokenUsage`**:
   * Clave compuesta: `org_id` + `month` (Reemplaza la granularidad previa sólo por `user_id`).
   * `tokens_used`: `int`.

5. **Actualización en `PRScore`**:
   * Añadir `org_id`: `str | None` (Indexado).
   * Añadir `agent_id`: `str | None` (Indexado, proveniente del header `X-WatchGate-Agent-ID`).

6. **Aislamiento en `SemanticCache`**:
   * Clave primaria compuesta: `(org_id, diff_hash)`.

---

## 4. Servidor MCP Nativo en `stdio` (`watchgate/mcp/`)

Se creará el módulo `watchgate/mcp/` habilitando el estándar **Model Context Protocol** como un adaptador fino sobre la capa de servicio de aplicación.

### 4.1 Estructura del Módulo `watchgate/mcp/`
```
watchgate/mcp/
├── __init__.py
├── server.py             # Instancia principal del servidor MCP (usando SDK `mcp`)
├── transports/
│   └── stdio.py          # Transporte de E/S estándar para agentes locales / IDEs
├── tools/
│   ├── analyze.py        # Herramienta MCP: watchgate_analyze_diff
│   ├── precheck.py       # Herramienta MCP: watchgate_precheck
│   ├── explain.py        # Herramienta MCP: watchgate_explain_risk
│   ├── verify.py         # Herramienta MCP: watchgate_verify_fix
│   └── rag.py            # Herramienta MCP: watchgate_query_threat_kb
└── cli.py                # Entrypoint CLI: watchgate mcp serve [--transport stdio]
```

### 4.2 Herramientas MCP Expuestas
* **`watchgate_analyze_diff`**: Analiza un parche `git diff` y devuelve el riesgo y la guía `AgentGuidance`.
* **`watchgate_precheck`**: Resultado ultra-rápido (<100ms) de capas Estática + Dependencias.
* **`watchgate_explain_risk`**: Explicación del patrón de amenaza para la regla `rule_id` dada.
* **`watchgate_verify_fix`**: Evaluación de resolución de hallazgos mediante firma sintáctica.
* **`watchgate_query_threat_kb`**: Consulta de patrones de ataque en el corpus RAG local.

---

## 5. Endpoints REST y Esquemas de Adaptación (`watchgate/api/routers/agent.py`)

Añadir el router dedicado `/api/v1/agent` dentro de `watchgate/api/`.

### 5.1 Rutas REST
1. **`POST /api/v1/agent/precheck`**:
   * Ejecuta solo las capas deterministas (`static`, `dependencies`). Respuesta < 100 ms. Cero consumo LLM.
2. **`POST /api/v1/agent/analyze`**:
   * Ejecuta el pipeline de análisis mediante `QuotaService`. Retorna `AggregatedResult` mapeado junto con `AgentGuidance`.
3. **`POST /api/v1/agent/verify-fix`**:
   * Recibe el parche previo (`original_diff`) y el nuevo parche candidato (`candidate_diff`).
   * **Algoritmo de Matching**: Compara firmas de hallazgos basadas en `rule_id` + `file_path` + `code_hunk_hash` (en lugar de líneas absolutas) para determinar cuáles hallazgos fueron efectivamente resueltos.
   * Retorna delta de riesgo (`risk_reduced: bool`, `resolved_findings`, `remaining_findings`).
4. **`GET /api/v1/agent/policy`**:
   * Devuelve las políticas de la organización (umbrales, reglas activas y cuota de tokens restante).

### 5.2 Esquemas de Adaptación (`watchgate/api/schemas/agent.py`)

```python
class ActionableStep(BaseModel):
    file_path: str
    line: int | None = None
    problem: str
    suggested_action: str

class AgentGuidance(BaseModel):
    is_mergeable: bool
    recommended_action: str  # "PROCEED", "RETRY_WITH_FIX", "BLOCK_HUMAN_REVIEW"
    summary_for_agent: str
    actionable_steps: list[ActionableStep] = Field(default_factory=list)

class AgentAnalyzeResponse(BaseModel):
    analysis: AggregatedResult
    guidance: AgentGuidance
```

---

## 6. Servicio de Cuotas y Modo Degradado Inteligente (Opción B)

### 6.1 Implementación en `watchgate/service/quota.py`
Se crea la capa de servicio `QuotaService` que envuelve la invocación al Core Engine:

1. Antes de ejecutar la capa semántica, `QuotaService` consulta el consumo acumulado del mes para la `org_id` en `UserTokenUsage`.
2. Se compara `tokens_used` contra `organization.monthly_token_quota`.
3. **Si `tokens_used >= monthly_token_quota`**:
   * Se activa el **Modo Degradado Inteligente**.
   * Se omite la capa semántica (`semantic.skipped = True`, `skip_reason = "Cuota mensual de tokens alcanzada. Modo Degradado Determinista activo."`).
   * Se ejecutan las capas deterministas (**Estática**, **Dependencias** y **Reputación**).
   * Se re-normalizan los pesos de las 3 capas activas según la fórmula $w'_i = \frac{w_i}{\sum w_k}$.
   * Se retorna `HTTP 200 OK` con un aviso explícito en la respuesta.
4. **Imputación Atómica**: El incremento de uso de tokens post-análisis se realiza mediante `UPDATE user_token_usage SET tokens_used = tokens_used + :inc WHERE org_id = :org_id AND month = :month`.

---

## 7. Matriz de Riesgos y Mitigaciones Actualizada

| Riesgo | Probabilidad | Impacto | Mitigación Incorporada en el Diseño |
|---|---|---|---|
| **Condición de carrera en consumo de cuotas** | Media | **Crítico** | Imputación atómica mediante SQL `UPDATE ... SET tokens_used = tokens_used + :inc`. |
| **Fuga de caché semántica entre tenants** | Media | **Crítico** | Clave primaria compuesta en `SemanticCache`: `(org_id, diff_hash)`. |
| **Falsos negativos en `/verify-fix` por desplazamiento de líneas** | Media | **Medio** | Coincidencia de hallazgos por firma (`rule_id` + `file_path` + `hunk_hash`) en lugar de líneas absolutas. |
| **Contaminación del Core con conceptos de SaaS** | Alta | **Alto** | Ubicar `AgentGuidance` y lógica de cuotas exclusivamente en `watchgate/api` y `watchgate/service`. |
| **Desincronización de esquema de BD en Dashboard** | Media | **Medio** | Unificar la capa de acceso a datos utilizando SQLModel (`watchgate/db/`). |

---

## 8. Plan de Implementación Recomendado Fase a Fase

### **Fase 1: Capa de Datos Multi-Tenant & Autenticación**
* **Objetivo**: Extender SQLModel con `Organization`, `org_id`, `default_agent_name`, actualización atómica de tokens y `SemanticCache` multi-tenant.
* **Módulos Afectados**: `watchgate/db/models.py`, `watchgate/db/repository.py`, `watchgate/api/auth.py`.
* **Validación**: Tests unitarios de aislamiento multi-tenant e incrementos atómicos (`tests/unit/test_db_multitenant.py`).

### **Fase 2: Capa de Servicio de Cuotas & Modo Degradado (Opción B)**
* **Objetivo**: Implementar `QuotaService` para gestionar la cuota por `org_id` con re-normalización de pesos y fallback determinista con HTTP 200 OK.
* **Módulos Afectados**: `watchgate/service/quota.py`, `watchgate/core/cost_control.py`.
* **Validación**: Test de simulación de agotamiento de presupuesto (`tests/unit/test_quota_degraded.py`).

### **Fase 3: Adaptadores y Endpoints REST para Agentes**
* **Objetivo**: Implementar `/api/v1/agent/precheck`, `/analyze`, `/verify-fix` (con matching por firma) y esquemas `AgentGuidance`.
* **Módulos Afectados**: `watchgate/api/schemas/agent.py`, `watchgate/api/routers/agent.py`, `watchgate/api/main.py`.
* **Validación**: Tests de integración de la API REST para agentes (`tests/integration/test_agent_api.py`).

### **Fase 4: Servidor MCP Nativo en `stdio`**
* **Objetivo**: Crear módulo `watchgate/mcp/` con las 5 herramientas y transporte `stdio`. Añadir comando CLI `watchgate mcp serve`.
* **Módulos Afectados**: `watchgate/mcp/`, `watchgate/cli.py`, `pyproject.toml`.
* **Validación**: Test de invocación de herramientas MCP mediante cliente de prueba (`tests/unit/test_mcp_server.py`).

### **Fase 5: Métricas Multi-Tenant en Dashboard & Documentación**
* **Objetivo**: Visualización de métricas por organización e historial de agentes en el Dashboard. Crear manual de integración MCP.
* **Módulos Afectados**: `watchgate/dashboard/backend/routers/`, `docs/manual_mcp.md`.
* **Validación**: Verificación manual del dashboard y compilación de documentación.

---

## 9. Criterios de Aceptación y Verificación

1. **Aislamiento Multi-Tenant**: Confirmar que la Organización A no puede leer ni reutilizar análisis o cachés de la Organización B.
2. **Concurrencia de Tokens**: Validar con 10 peticiones simultáneas que la suma de `tokens_used` en BD es exactamente la esperada sin pérdidas por *lost update*.
3. **Modo Degradado**: Comprobar que al superar la cuota el análisis devuelve HTTP 200 OK con capas deterministas, re-normalización de pesos y `semantic.skipped = True`.
4. **Servidor MCP (`stdio`)**: Invocación exitosa de herramientas MCP vía `stdio`.
5. **Verificación de Fix Robusta**: Comprobar que `/agent/verify-fix` detecta la solución de un problema incluso si el código fue movido de línea.
6. **Preservación del Core**: Verificar que `watchgate.core` no contiene dependencias hacia `watchgate.api` ni `watchgate.db`.
7. **Calidad de Código**: `pytest`, `ruff check .` y `mypy watchgate` ejecutados sin errores.
