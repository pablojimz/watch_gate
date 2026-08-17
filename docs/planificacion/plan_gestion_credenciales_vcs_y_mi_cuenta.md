# Plan de Implementación: Gestión de Credenciales de GitHub por Usuario y Rediseño de "Mi Cuenta"

**Documento de Planificación Técnica y Arquitectura**  
**Fecha**: Agosto 2026  
**Ubicación**: `docs/planificacion/plan_gestion_credenciales_vcs_y_mi_cuenta.md`  

---

## 1. Resumen Ejecutivo y Objetivos

El objetivo de este plan es adaptar **WatchGate** para soportar la gestión de credenciales de Control de Versiones (VCS / GitHub API) a nivel **por usuario**, permitiendo que cada desarrollador (con cualquier rol: `revisor`, `mantenedor` o `admin_organizacion`) vincule su propio **Personal Access Token (PAT)** de GitHub y configure la URL de su servidor (GitHub Enterprise o `api.github.com`). 

Además, se rediseña la interfaz web introduciendo la vista **"Mi Cuenta" (`/user-settings`)** para la personalización de credenciales y tema local, manteniendo la vista **"Administración" (`/admin`)** reservada exclusivamente para la gobernanza global de la organización.

---

## 2. Arquitectura de Ámbitos y Permisos

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DASHBOARD DE WATCHGATE                            │
├──────────────────────────────────────────────┬──────────────────────────────┤
│          ÁMBITO DE USUARIO (Todos)           │   ÁMBITO DE ORGANIZACIÓN     │
│             `/user-settings`                 │        (Solo Admin `/admin`) │
├──────────────────────────────────────────────┼──────────────────────────────┤
│ - Personal Access Token (PAT) de GitHub      │ - Proveedor LLM corporativo  │
│ - URL de API de GitHub (Enterprise/Public)   │ - Presupuesto mensual org    │
│ - Preferencias de Tema Visual Local          │ - Token Fallback de Org      │
│ - Datos de Perfil (nombre, login, rol)       │ - Logo corporativo & Roles   │
└──────────────────────────────────────────────┴──────────────────────────────┘
```

---

## 3. Jerarquía de Resolución de Credenciales de GitHub

Cuando el sistema necesita realizar peticiones HTTP a GitHub (descarga de diffs, cálculo de reputación, escaneos de repositorios):

```
 ┌─────────────────────────────────────────────────────────────┐
 │ 1. Token Personal del Usuario actual (`user.github_token`)  │
 └──────────────────────────────┬──────────────────────────────┘
                                │ (Si no está configurado)
                                ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ 2. Token de la Conexión VCS del Repositorio (`vcs.token`)   │
 └──────────────────────────────┬──────────────────────────────┘
                                │ (Si no está configurado)
                                ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ 3. Token Fallback de la Organización (`org.github_token`)   │
 └──────────────────────────────┬──────────────────────────────┘
                                │ (Si no está configurado)
                                ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ 4. Variables de Entorno (`WATCHGATE_GITHUB_TOKEN`)          │
 └──────────────────────────────┬──────────────────────────────┘
                                │ (Si no está configurado)
                                ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ 5. Petición Anónima / Sin Autenticar (Límite: 60 req/h)     │
 └─────────────────────────────────────────────────────────────┘
```

---

## 4. Cambios Técnicos por Módulo

### 4.1 Núcleo y Adaptador (`watchgate/`)
- **`watchgate/config.py`**:
  - Extender `WatchGateConfig` con `github_token: str | None` y `github_api_url: str`.
- **`watchgate/adapters/github_client.py`**:
  - `GitHubClient.__init__(token: str | None = None, api_url: str | None = None)`.
  - Reemplazar la constante rígida `_API_BASE` por la propiedad de instancia `self._api_base`.
- **`watchgate/cli.py`**:
  - Banderas CLI opcionales `--github-token` y `--github-api-url`.

### 4.2 Persistencia y Backend (`watchgate/dashboard/backend/`)
- **`models.py` (`DashboardUser`)**:
  - `github_api_url: Mapped[str | None]`
  - `github_token: Mapped[str | None]` (cifrado con Fernet `EncryptedString`)
  - `ui_settings_json: Mapped[str | None]`
- **`schemas.py`**:
  - `UserSettingsOut`: `login`, `display_name`, `role`, `github_api_url`, `github_token_set`, `github_token_masked`, `ui_settings`.
  - `UserSettingsIn`: `display_name`, `github_api_url`, `github_token`, `clear_github_token`, `ui_settings`.
- **`alembic_dashboard/versions/`**:
  - Migración para añadir las columnas anulables en `dashboard_users`.
- **`routers/user_settings.py`**:
  - `GET /settings/user`: Obtener configuración del usuario logueado.
  - `PUT /settings/user`: Guardar personalización de usuario.

### 4.3 Frontend (`watchgate/dashboard/frontend/`)
- **`AppLayout.tsx`**: Añadir enlace **"Mi Cuenta"** (`/user-settings`) a la barra de navegación para todos los usuarios.
- **`UserSettingsPage.tsx`**: Formulario interactivo de 3 secciones (Conexión GitHub, Apariencia Local, Perfil).
- **`AdminPage.tsx`**: Mantener exclusivamente controles de administración de la organización.
- **`locales/es.json`**: Cadenas i18n para los nuevos formularios y campos.

---

## 5. Matriz de Seguridad y Permisos

| Endpoint / Funcionalidad | Permiso | Cifrado / Enmascaramiento |
| :--- | :--- | :--- |
| `GET/PUT /settings/user` | Cualquier usuario autenticado (`CurrentUser`) | Tokens cifrados en DB (Fernet) y enmascarados en respuesta HTTP (`ghp_1234…5678`). |
| `GET/PUT /settings/llm` | Exclusivo `admin_organizacion` | Clave LLM enmascarada. |
| `GET/PUT /settings/ui` | Exclusivo `admin_organizacion` (UI global / Logo) | N/A |

---

## 6. Condiciones y Requisitos Obligatorios de Implementación (Auditoría Senior)

Para garantizar la seguridad, resiliencia y estabilidad del sistema antes de proceder con el desarrollo, la implementación debe cumplir estrictamente las siguientes **4 Condiciones Obligatorias**:

1. **Condición 1 — Cifrado Criptográfico Estricto**:
   - Toda columna en base de datos que almacene un token de usuario (`github_token`) debe utilizar el tipo SQLAlchemy `EncryptedString` (basado en Fernet y cargado desde `WATCHGATE_DB_SECRET`).
   - Ningún token viajará en claro en respuestas HTTP (`github_token_masked`).
2. **Condición 2 — Protección SSRF en URLs de API**:
   - El validador Pydantic de `github_api_url` debe validar la sintaxis URI e rechazar explícitamente rangos de IP privadas (RFC 1918, `169.254.169.254`, `localhost`) excepto cuando esté activo el modo de desarrollo (`WATCHGATE_DASHBOARD_DEV_MODE=1`).
3. **Condición 3 — Propagación de Credenciales en Trabajos Asíncronos (Redis RQ)**:
   - Al encolar tareas asíncronas en Redis RQ (`tasks.py`), el endpoint HTTP solicitante debe resolver las credenciales de GitHub e inyectarlas explícitamente en la tarea, asegurando que las tareas background no pierdan el contexto de usuario.
4. **Condición 4 — Prueba de Aislamiento de Permisos (RBAC)**:
   - Se debe incluir una prueba unitaria e integrada que demuestre que un usuario con rol `revisor` o `mantenedor` (ej. la cuenta demo `reviewer`) puede actualizar su perfil personal en `/settings/user`, pero recibe un rechazo `403 Forbidden` si intenta acceder o modificar `/settings/llm` o la configuración global de la organización.

