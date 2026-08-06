# Plan de Implementación: Sistema de Engine API por Usuario (SaaS Ready)

## Metadatos

- **Autor / Responsable**: Equipo de Arquitectura e Ingeniería de WatchGate
- **Estado**: Especificación Técnica Aprobada / Auditoría de Arquitectura Completada
- **Fecha de creación**: 2026-08-06
- **Última actualización**: 2026-08-06
- **Objetivo**: Definir la arquitectura de servicios separados, persistencia unificada con `SQLModel`, ingesta robusta de diffs con `unidiff`, servidor RAG distribuido, seguridad de logs y mapa de endpoints para el despliegue de WatchGate SaaS.

---

# 1. Justificación Arquitectónica: Separación de Servicios

En una arquitectura limpia, robusta y escalable para producción o SaaS, **el Engine API (procesamiento de análisis e IA) y el Dashboard Backend (gestión web para humanos) son dos servicios independientes**:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                 CLIENTES CI / CD                                │
│          [CLI / Runner CI]           [GitHub App]           [Webhooks]          │
└──────────────────────────────────────┬──────────────────────────────────────────┘
                                       │
                                       │ Authorization: Bearer wg_live_...
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      SERVICIOS DE WATCHGATE (SEPARADOS)                         │
│                                                                                 │
│ ┌─────────────────────────────────────────┐   ┌───────────────────────────────┐ │
│ │  Engine API Server (watchgate/api/)     │   │ Dashboard (dashboard/backend/)│ │
│ │                                         │   │                               │ │
│ │  - Autenticación: Bearer API Keys       │   │ - Autenticación: OAuth2/Cookie │ │
│ │  - Carga: Alta (E/S, LLMs, RAG)         │   │ - Carga: Lectura ligera (UI)  │ │
│ │  - Endpoints: /v1/analyze, /webhooks    │   │ - Endpoints: /scores, /repos  │ │
│ └────────────────────┬────────────────────┘   └───────────────┬───────────────┘ │
└──────────────────────┼────────────────────────────────────────┼─────────────────┘
                       │                                        │
                       ▼                                        ▼
┌───────────────────────────────────────────┐   ┌─────────────────────────────────┐
│ Core Pipeline (watchgate/core/pipeline)   │   │ Persistencia Unificada          │
│ Inferencia paralelizada de capas de IA    │   │ (watchgate/db/ - SQLModel)      │
└───────────────────────────────────────────┘   │ Histórico, Keys, Tokens, Cache  │
                                                └─────────────────────────────────┘
```

## 1.1 Principios Clave de Arquitectura Senior:

1. **Aislamiento de Cargas de Trabajo (Workload Isolation)**:
   - **Engine API (`watchgate/api/`)**: Realiza cómputos intensivos (procesamiento de diffs, llamadas a LLMs con latencias de 1-3 segundos, vector search RAG en ChromaDB).
   - **Dashboard Backend (`watchgate/dashboard/backend/`)**: Sirve datos ligeros a la interfaz React en milisegundos (gráficos, histórico, listas de repositorios).
   - *Beneficio*: Una ráfaga de 100 PRs simultáneas en CI/CD procesadas por el Engine API **nunca ralentizará ni bloqueará la experiencia de los usuarios navegando por el Dashboard**.

2. **Diferenciación de Seguridad y Contextos de Autenticación**:
   - **Engine API**: Autentica **máquinas/servidores** mediante **Bearer API Keys** (`wg_live_...`) o firmas **HMAC Webhook** (`X-Hub-Signature-256`).
   - **Dashboard Backend**: Autentica **usuarios humanos** mediante **OAuth2/OIDC** (GitHub/Auth0/Keycloak) emitiendo cookies de sesión firmadas.

3. **Escalabilidad Horizontal Independiente**:
   - El Engine API puede escalarse agregando más pods/contenedores según el volumen de análisis en horas pico de desarrollo.

---

# 2. Estructura de Paquetes Unificada

Para cumplir la **Condición 1 de la Auditoría** y evitar la existencia de dos bases de datos inconexas (`cost.db` vs `app.db`), se crea el paquete unificado `watchgate/db/` que concentra toda la persistencia:

```
watchgate/
├── core/                                # NÚCLEO AGNÓSTICO (models, pipeline, orchestrator, layers)
│   ├── pipeline.py                      # run_full_analysis()
│   ├── cost_control.py                  # Control de presupuesto (consume watchgate/db/)
│   └── diffparser.py                    # parse_diff() y parse_diff_from_text() con unidiff
│
├── db/                                  # [PAQUETE UNIFICADO DE PERSISTENCIA]
│   ├── __init__.py
│   ├── connection.py                    # Motor SQLAlchemy / SQLite / Postgres híbrido
│   ├── models.py                        # Modelos SQLModel (Users, APIKeys, TokenUsage, SemanticCache, PRScores)
│   └── repository.py                    # Consultas y escrituras reutilizables
│
├── api/                                 # ENGINE API (Servicio de Análisis e IA)
│   ├── main.py                          # App FastAPI con middleware de sanitización de logs y max payload (10 MB)
│   ├── auth.py                          # Middleware de API Keys (wg_live_...) & Scopes
│   ├── dependencies.py                  # Inyección de dependencias
│   ├── routers/
│   │   ├── analyze.py                   # POST /api/v1/analyze (con BackgroundTasks)
│   │   └── webhooks.py                  # POST /api/v1/webhooks/github (HMAC verification)
│   └── services/
│       ├── api_key_service.py           # Validación SHA-256 de claves
│       └── usage_service.py             # Imputación de consumo de tokens por usuario
│
└── dashboard/                           # SERVICIO DEL PANEL WEB (Dashboard UI)
    └── backend/                         # Backend para la interfaz humana React
        ├── main.py                      # App FastAPI del Dashboard UI
        ├── auth.py                      # OAuth GitHub / OIDC + Cookie de Sesión JWT
        └── routers/
            ├── scores.py                # GET /repos/{repo}/scores
            ├── keys.py                  # POST, GET, DELETE /keys (Gestión UI de API Keys)
            └── feedback.py              # POST /feedback (Registro de falsos positivos)
```

---

# 3. Cumplimiento de las 5 Condiciones Obligatorias de la Auditoría

### Condición 1: Unificación de Persistencia en `watchgate/db/`
- Se elimina la base de datos independiente `.watchgate/cost.db` de `CostController`.
- La tabla de caché de respuestas semánticas (`semantic_cache`) y la de uso de tokens (`user_token_usage`) se integran en el módulo común `watchgate/db/`.

### Condición 2: Ingesta de Diffs en Texto Plano con la Librería `unidiff`
- Se añade la dependencia ligera `unidiff` a `pyproject.toml`.
- `parse_diff_from_text(diff_text: str, base_sha: str, head_sha: str) -> NormalizedDiff` en `watchgate/core/diffparser.py` utiliza `PatchSet.from_string(diff_text)` para procesar parches unificados con garantías frente a caracteres no-ASCII, renombres y binarios.

### Condición 3: Modelos Únicos Sincronizados con `SQLModel`
- Se adopta **SQLModel** (librería oficial que fusiona Pydantic v2 y SQLAlchemy 2.0) en `watchgate/db/models.py`.
- Un solo modelo define la tabla de base de datos y la validación Pydantic del contrato de la API, eliminando la duplicación de código y el riesgo de desincronización.

### Condición 4: Soporte de RAG Cliente/Servidor Distribuido (`WATCHGATE_CHROMA_URL`)
- Se actualizan `watchgate/core/rag/retriever.py` e `indexer.py` para inspeccionar la variable `WATCHGATE_CHROMA_URL`:
  - Si la variable está definida (ej. `http://chroma.internal:8000`), utiliza `chromadb.HttpClient`.
  - Si no está definida, utiliza `chromadb.PersistentClient(path=index_path)` para ejecución local.
- Esto permite escalar el Engine API a $N$ contenedores en Kubernetes compartiendo el mismo servidor de vector search RAG.

### Condición 5: Protección de Logs y Límite de Payload (10 MB)
- En `watchgate/api/main.py`:
  1. Middleware de tamaño máximo de petición: Rechaza peticiones HTTP mayores a 10 MB con estado `413 Payload Too Large`.
  2. Filtro de Logging Criptográfico: Intercepta todos los logs del sistema y reemplaza cualquier coincidencia con expresiones regulares de API Keys (`wg_live_[a-f0-9]{64}`, `sk-ant-*`, `AIzaSy*`) por `[REDACTED_SECRET]`.

---

# 4. Esquema de Base de Datos Unificado con SQLModel (`watchgate/db/models.py`)

```python
from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel

# Usuarios del sistema
class User(SQLModel, table=True):
    __tablename__ = "users"
    id: str = Field(primary_key=True)
    email: str = Field(index=True, unique=True)
    name: str
    role: str = Field(default="revisor")  # admin_organizacion | mantenedor | revisor
    custom_llm_api_key: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

# Vault de API Keys por Usuario (almacenamiento mediante hash SHA-256)
class UserAPIKey(SQLModel, table=True):
    __tablename__ = "user_api_keys"
    id: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    name: str
    key_prefix: str  # Ej: "wg_live_4a8f"
    key_hash: str = Field(unique=True, index=True)  # SHA-256(token_crudo)
    scopes: str = Field(default="analysis:write,scores:read")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None

# Consumo de tokens por usuario
class UserTokenUsage(SQLModel, table=True):
    __tablename__ = "user_token_usage"
    user_id: str = Field(foreign_key="users.id", primary_key=True)
    month: str = Field(primary_key=True)  # "YYYY-MM"
    tokens_used: int = Field(default=0)

# Caché de resultados semánticos (unificada desde CostController)
class SemanticCache(SQLModel, table=True):
    __tablename__ = "semantic_cache"
    diff_hash: str = Field(primary_key=True)
    output_json: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

# Histórico de puntuaciones de análisis
class PRScore(SQLModel, table=True):
    __tablename__ = "pr_scores"
    id: str = Field(primary_key=True)
    repo: str = Field(index=True)
    pr_id: str
    user_id: Optional[str] = Field(foreign_key="users.id", default=None)
    score: int
    semaforo: str
    layer_results_json: str
    weights_used_json: str
    timestamp: datetime = Field(default_factory=datetime.utcnow, index=True)
```

---

# 5. Persistencia Asíncrona y Desempeño HTTP (`POST /api/v1/analyze`)

Para minimizar la latencia de respuesta en la API HTTP, la persistencia en base de datos del resultado (`pr_scores`) y la actualización del saldo de tokens (`user_token_usage`) **se ejecutan de forma asíncrona mediante `BackgroundTasks` de FastAPI**:

```python
@router.post("/api/v1/analyze", response_model=AggregatedResult)
async def analyze_pr(
    request: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    user: UserContext = Depends(get_current_user_from_api_key)
):
    # 1. Parseo del diff e invocación síncrona/concurrente del núcleo
    diff = parse_diff_from_text(request.diff_text, request.base_sha, request.head_sha)
    result = run_full_analysis(diff, request.metadata, request.config)

    # 2. Persistencia diferida en segundo plano (No bloquea la respuesta HTTP)
    background_tasks.add_task(
        save_score_and_update_tokens, 
        result=result, 
        user_id=user.id
    )

    # 3. Retorno inmediato al cliente (Latencia reducida)
    return result
```

---

# 6. Análisis Comparativo de Persistencia: SQLite vs. PostgreSQL

## 6.1 Elección del Motor de Persistencia

| Criterio | SQLite (con modo WAL y `timeout=30.0`) | PostgreSQL (Nativo Producción) |
|---|---|---|
| **Arquitectura de Servidores** | Basado en archivo único local. Proceso en el mismo servidor. | Servidor de base de datos independiente (Managed Instance). |
| **Escalabilidad Horizontal (Multi-nodo)** | ❌ **No posible**. Múltiples réplicas de la API no pueden escribir sobre un archivo único sin bloqueos de red NFS/EFS. | ✅ **Nativa**. $N$ pods del Engine API se conectan simultáneamente mediante *Connection Pooling* (`pgbouncer`). |
| **Escrituras Concurrentes** | ⚠️ **Bloqueo a nivel de archivo**. Un *writer* bloquea a otros escrituras. | ✅ **Control de Concurrencia Multiversión (MVCC)**. Maneja miles de escrituras simultáneas por segundo sin bloqueos. |
| **Integridad de Datos y Backup** | Requiere copias de archivo estáticas con `VACUUM INTO`. | Backups continuos Point-In-Time Recovery y alta disponibilidad con replicas de lectura. |
| **Facilidad de Desarrollo / Testing** | ✅ **Máxima ligereza**. Ejecutable en memoria (`:memory:`) sin dependencias externas ni Docker. | Requiere levantar un servicio Postgres local o un contenedor Docker. |

## 6.2 Estrategia Híbrida con SQLModel / SQLAlchemy
- **Entorno de Desarrollo, CLI Local y Pruebas Unitarias**: **SQLite** (con `PRAGMA journal_mode=WAL` y `timeout=30.0`).
- **Entorno de Despliegue SaaS / Producción**: **PostgreSQL** mediante `WATCHGATE_DATABASE_URL=postgresql://user:pass@postgres-host/watchgate`.

---

# 7. Endpoints por Servicio

## 7.1 Endpoints del Engine API (`watchgate/api/`)
Autenticados mediante `Authorization: Bearer wg_live_...`:
- `POST /api/v1/analyze`: Ejecuta el análisis recibiendo `diff_text` o referencias SHA.
- `POST /api/v1/webhooks/github`: Receptor de eventos de GitHub Apps / Webhooks con validación HMAC `X-Hub-Signature-256`.

## 7.2 Endpoints del Dashboard Backend (`watchgate/dashboard/backend/`)
Autenticados mediante Cookies de Sesión JWT (OAuth/OIDC):
- `GET /auth/github/login` & `GET /auth/github/callback`: Autenticación SSO.
- `GET /repos/{repo}/scores`: Consulta del histórico de análisis para la UI.
- `POST /feedback`: Registro de confirmaciones o falsos positivos (RAG dinámico).
- `POST /keys`, `GET /keys`, `DELETE /keys/{id}`: Gestión de API Keys desde la UI del usuario.

---

# 8. Hoja de Ruta e Implementación por Fases

- [ ] **Fase 1: Paquete Unificado de Persistencia (`watchgate/db/`)**
  - Añadir `SQLModel` a `pyproject.toml`.
  - Crear `watchgate/db/connection.py`, `models.py` (con los 5 modelos SQLModel) y `repository.py`.

- [ ] **Fase 2: Extensión de `diffparser.py` con `unidiff`**
  - Añadir `unidiff` a `pyproject.toml`.
  - Implementar `parse_diff_from_text()` utilizando `unidiff.PatchSet.from_string()` con manejo robusto de excepciones de decodificación.

- [ ] **Fase 3: Construcción del Engine API (`watchgate/api/`)**
  - Crear `watchgate/api/main.py` con middleware de filtro de logs criptográfico y límite de payload de 10 MB.
  - Implementar `auth.py` con autenticación por API Key SHA-256.
  - Crear `routers/analyze.py` con ejecución asíncrona mediante `BackgroundTasks`.

- [ ] **Fase 4: Soporte de RAG Distribuido (`WATCHGATE_CHROMA_URL`)**
  - Actualizar `retriever.py` e `indexer.py` para soportar `chromadb.HttpClient` cuando exista la variable de entorno `WATCHGATE_CHROMA_URL`.

- [ ] **Fase 5: Gestión de API Keys en el Dashboard y Webhooks**
  - Implementar `/keys` en `dashboard/backend/routers/keys.py`.
  - Implementar `/api/v1/webhooks/github` en `watchgate/api/routers/webhooks.py` con verificación HMAC.
