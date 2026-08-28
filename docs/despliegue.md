# Despliegue

Este documento cubre cómo desplegar WatchGate más allá de un checkout local
con Poetry -- Docker/`docker-compose.yml` para levantar el stack completo, y
la lista de variables de entorno que hay que revisar antes de considerar un
despliegue "de producción".

No prescribe un proveedor de hosting concreto (Railway, Fly.io, un VPS,
Kubernetes...) -- las imágenes son estándar y corren en cualquiera; qué
plataforma usar sigue siendo una decisión del equipo, no de este documento.

## Los 4 servicios desplegables

| Servicio | Qué es | Imagen | Puerto por defecto |
|---|---|---|---|
| **Engine API** | API REST que exponen los adaptadores externos (GitHub Action, agentes de IA vía `/api/v1/agent/*`, un hook `pre-receive` delegando a un servidor central) para analizar diffs sin instalar la CLI en cada sitio | `docker/engine-api.Dockerfile` | 8080 |
| **Dashboard backend** | API del panel de control (login, histórico de scores, settings, gestión de API keys) | `docker/dashboard-backend.Dockerfile` | 8000 |
| **Dashboard frontend** | SPA React/Vite, build estático servido por nginx, que reenvía `/api/*` al backend | `watchgate/dashboard/frontend/Dockerfile` | 80 (nginx) |
| **Postgres** | Aloja **dos** bases de datos separadas: `watchgate` (esquema SQLModel, compartido por Engine API y Dashboard backend) y `watchgate_dashboard` (esquema propio del Dashboard). SQLite es el default de desarrollo local, un fichero por proceso | imagen oficial `postgres` | 5432 |

La CLI (`watchgate analyze`) y el adaptador de GitHub Action no son
servicios de larga duración -- corren dentro del propio pipeline de CI/CD
del repo que se está analizando, no hace falta desplegarlos aparte.

## Arrancar el stack completo en local (Docker Compose)

```bash
cp .env.example .env
# Rellena como mínimo WATCHGATE_LLM_API_KEY (capa semántica) -- el resto
# de variables tienen defaults razonables para un stack de prueba local.
docker compose up --build
```

- Dashboard: <http://localhost:5173>
- Engine API: <http://localhost:8080/health>
- Dashboard backend: <http://localhost:8000/api/health>

`docker-compose.yml` conecta Engine API y Dashboard backend contra el
Postgres del propio compose (`WATCHGATE_DATABASE_URL`/
`WATCHGATE_DASHBOARD_DATABASE_URL`) -- es la primera vez que el soporte
Postgres del proyecto corre contra una instancia real de forma reproducible
para cualquiera, no solo a mano en el entorno de quien lo implementó
originalmente. Ya está también en el pipeline de CI (`postgres-test` en
`ci.yml`, contra un servicio Postgres real del propio runner) además de
`docker compose up` -- el resto de jobs de CI siguen usando SQLite para la
suite completa, más rápido y sin infraestructura extra que levantar en
cada push.

**Dos bases de datos, no una**: el esquema propio del Dashboard
(`watchgate/dashboard/backend/db.py`) y el esquema SQLModel compartido
(`watchgate/db/models.py`, usado por Engine API y por la gestión de API
keys del Dashboard) definen ambos una tabla llamada `pr_scores`, con
columnas completamente distintas e incompatibles entre sí. Si
`WATCHGATE_DATABASE_URL` y `WATCHGATE_DASHBOARD_DATABASE_URL` apuntasen a
la misma base de datos de Postgres, la segunda tabla `pr_scores` que se
intenta crear chocaría con la primera -- el propio chequeo de esquema
(`_check_schema_matches_models()`) lo detecta y aborta el arranque con un
`SchemaOutOfDateError` listando columnas "faltantes" que en realidad
pertenecen al otro esquema. Por eso `docker-compose.yml` provisiona la
base de datos `watchgate` (para el esquema SQLModel) y, vía
`docker/postgres-init/01-create-dashboard-db.sql`, una segunda base
`watchgate_dashboard` (para el esquema propio del Dashboard) en el mismo
servidor Postgres -- cero cambios de código en ninguno de los dos
esquemas. Verificado en vivo: `docker compose up --build` levanta los 4
servicios, los 3 endpoints HTTP (`/health`, `/api/health`, `/`) responden
200, y un login de desarrollo a través del proxy nginx del frontend
persiste sesión correctamente contra el backend real.

## TLS / reverse proxy en producción

`docker-compose.prod.yml` añade un servicio `reverse-proxy` (Caddy) delante
de todo el stack, con TLS automático:

```bash
export WATCHGATE_DOMAIN=watchgate.tuempresa.com   # DNS ya apuntando aquí
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

Con `WATCHGATE_DOMAIN` apuntando de verdad a la máquina (puerto 443
alcanzable desde internet), Caddy pide el certificado a Let's Encrypt solo
la primera vez y lo renueva solo. Sin dominio (o en local, el default es
`localhost`), sirve igual por HTTPS con un certificado de su propia CA
interna -- verificado en vivo (`curl -k https://localhost/api/v1/agent/policy`
llega de verdad a la Engine API, no a un 404); útil para probar el enrutado
antes de tener DNS configurado, pero un navegador lo marcará como no
confiable hasta importar esa CA. Rutas: `/api/v1/*` a la Engine API,
cualquier otra cosa al frontend del Dashboard (que a su vez ya sabe
reenviar su propio `/api/*` a `dashboard-backend`) -- ver
`docker/reverse-proxy/Caddyfile`.

> **Editar el `Caddyfile` no basta con `restart`/`caddy reload`.** El
> bind mount de `reverse-proxy` hacia `docker/reverse-proxy/Caddyfile`
> queda fijado al fichero que había en ese path cuando el contenedor se
> creó -- reproducido en vivo: tras editar el `Caddyfile` en disco (el fix
> de `encode gzip` para el endpoint SSE de refresco en vivo del Dashboard,
> ver `live_events.py`), ni un `docker exec ... caddy reload` ni un
> `docker compose restart reverse-proxy` lo recogían; `cat` dentro del
> contenedor seguía devolviendo el contenido antiguo. Hace falta recrear
> el contenedor para que Docker rehaga el mount contra el fichero actual:
> ```bash
> docker compose -f docker-compose.yml -f docker-compose.prod.yml \
>   up -d --force-recreate reverse-proxy
> ```
> Los datos (certificados TLS en el volumen `caddy_data`) no se tocan.

Antes se documentaba una configuración manual de nginx/Caddy sobre el host
(`docs/manual_despliegue_prod.md`) -- sigue siendo válida como referencia
si prefieres el reverse proxy fuera de Docker, pero ya no es el único
camino: `docker-compose.prod.yml` da un `up` con el que levantarlo todo
de una vez.

## Checklist de producción (`WATCHGATE_DASHBOARD_DEV_MODE=0`)

El propio proceso se niega a arrancar (`ensure_safe_startup_config()` en
`auth.py`) si falta cualquiera de estos, así que en la práctica es
imposible olvidarlos -- pero conviene saber por qué:

- `WATCHGATE_DASHBOARD_SECRET`: propio, ≥32 caracteres, nunca el valor por
  defecto del repo (`change-me-in-production`). Firma **y cifra** (AES-256-GCM)
  la cookie de sesión -- puede llevar embebido un token de acceso de GitHub.
- `WATCHGATE_DASHBOARD_SECURE_COOKIE=1`: exige servir por HTTPS de verdad
  (la cookie de sesión no se manda sin el flag `Secure` si esto no está
  activo) -- el overlay de arriba lo da gratis.
- `WATCHGATE_DASHBOARD_INGEST_TOKEN`: protege `POST /api/scores` (la vía
  por la que la Action persiste resultados en el dashboard).
- `WATCHGATE_DB_SECRET`: clave Fernet (32 bytes, `Fernet.generate_key()`)
  que cifra en la base de datos cualquier secreto que un usuario guarde
  (PAT de GitHub personal en Mi Cuenta, fallback de organización en
  Configuración, `access_token` de una `VCSConnection`). Sin ella,
  `watchgate/db/crypto.py` no falla al importarse (comodidad en local),
  pero el primer intento real de guardar uno de esos secretos revienta con
  un `RuntimeError` -- `ensure_safe_startup_config()` lo detecta al
  arrancar en vez de dejar que explote más tarde, opaco, en medio de un
  `PUT /api/settings/user`.

Además, ya activo por defecto en cualquier entorno (no solo producción):

- Rate limiting de `/api/auth/login`: 5 intentos fallidos / 5 min por
  usuario. **En memoria de proceso** -- si el dashboard backend se despliega
  algún día con más de una réplica detrás de un balanceador, cada réplica
  lleva su propio contador (protección real pero parcial, no compartida).
  No hace falta ningún cambio para un despliegue de una sola réplica.
- `init_db()` (tanto Engine API como Dashboard) se niega a arrancar si una
  base de datos ya existente no tiene las columnas que el código actual
  espera, en vez de fallar en silencio a mitad de una petición cualquiera
  -- ver "Migraciones de esquema" más abajo para resolverlo.

## Migraciones de esquema

Dos esquemas, dos entornos Alembic **separados** -- son dos bases de datos
físicamente distintas (`WATCHGATE_DATABASE_URL` vs
`WATCHGATE_DASHBOARD_DATABASE_URL`), cada una con su propio historial de
migraciones; compartir uno mezclaría el esquema de una dentro de la otra en
cuanto se corriera `upgrade head` contra el motor equivocado. Ambos usan
**Alembic** de verdad, con el mismo flujo:

**Esquema SQLModel** (`watchgate/db/` -- organizations, users,
user_api_keys, user_token_usage, repo_token_usage, semantic_cache,
pr_scores; lo usan Engine API y la gestión de API keys del Dashboard):

```bash
# Aplicar migraciones pendientes (local o dentro del contenedor):
make migrate                                    # local
docker compose exec engine-api alembic upgrade head   # Docker

# Generar una migración nueva tras cambiar watchgate/db/models.py:
make migration m="descripción del cambio"
```

**Esquema propio del Dashboard** (`watchgate/dashboard/backend/models.py`
-- pr_scores, repo_roles, repo_settings, org_settings, dashboard_users,
llm_settings, ui_settings), segundo entorno Alembic (`alembic_dashboard/`,
`alembic_dashboard.ini`):

```bash
# Aplicar migraciones pendientes (local o dentro del contenedor):
make migrate-dashboard                                                    # local
docker compose exec dashboard-backend alembic -c alembic_dashboard.ini upgrade head   # Docker

# Generar una migración nueva tras cambiar watchgate/dashboard/backend/models.py:
make migration-dashboard m="descripción del cambio"
```

**Importante para una base de datos que ya existía antes de adoptar
Alembic** (cualquier despliegue de antes de esta versión, en cualquiera de
las dos bases): las tablas ya están creadas, así que `upgrade head` no
debe volver a crearlas. Una sola vez, marca la base de datos como ya al
día sin ejecutar nada:

```bash
docker compose exec engine-api alembic upgrade head                                 # se
# encarga solo si hace falta -- si ya tenía las tablas de antes de Alembic:
docker compose exec engine-api alembic stamp head
docker compose exec dashboard-backend alembic -c alembic_dashboard.ini stamp head
```

Después de eso, `upgrade head` funciona con normalidad para cualquier
migración futura, en cualquiera de los dos esquemas. Deliberadamente **no
se ejecuta solo en cada arranque del contenedor** (a diferencia del
chequeo de `init_db()`, que sí es automático en ambos) -- aplicar un
cambio de esquema es un paso explícito de despliegue, no algo que deba
correr sin supervisión, sobre todo si algún día hay más de una réplica
arrancando a la vez contra la misma base de datos (mismo motivo por el que
se arregló el deadlock de `db_session()` del Dashboard, ver más abajo).

## Backups de Postgres

`docker-compose.prod.yml` incluye un servicio `postgres-backup`: `pg_dumpall`
diario (03:00 UTC por defecto) de **las dos bases del cluster** (`watchgate` +
`watchgate_dashboard`, más los roles) a un único fichero comprimido en el
volumen `postgres_backups`, con rotación (`WATCHGATE_BACKUP_RETENTION_DAYS`,
14 días por defecto). Corre un backup inicial nada más arrancar el
contenedor, no hace falta esperar a la primera medianoche.

```bash
# Ver los backups guardados:
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec postgres-backup ls -la /backups

# Forzar un backup manual (fuera del cron):
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec postgres-backup /usr/local/bin/backup.sh

# Cambiar la hora/retención:
export WATCHGATE_BACKUP_CRON="0 3 * * *"       # formato crontab, UTC
export WATCHGATE_BACKUP_RETENTION_DAYS=30
```

**Restaurar** (verificado en vivo: backup real -> restauración en un
Postgres nuevo -> datos reales recuperados, no solo "debería funcionar"):

```bash
# Sacar el backup del volumen a un fichero local:
docker compose -f docker-compose.yml -f docker-compose.prod.yml cp \
  postgres-backup:/backups/watchgate-<timestamp>.sql.gz ./watchgate-backup.sql.gz
gunzip watchgate-backup.sql.gz

# Contra un Postgres YA VACÍO (pg_dumpall incluye CREATE DATABASE/CREATE
# ROLE -- no lo ejecutes contra el Postgres que ya está sirviendo tráfico,
# o los CREATE DATABASE fallarán porque las bases ya existen):
psql -h <host> -U postgres -f watchgate-backup.sql
```

### Copia fuera de la máquina (S3 o compatible)

Sin `WATCHGATE_BACKUP_S3_BUCKET`, el volumen `postgres_backups` sigue
siendo el único sitio con el backup -- protege de un error humano/de
aplicación (borrar una fila por accidente, una migración mal aplicada),
pero no de perder la máquina entera. Con la variable puesta, cada backup
se sube además a un bucket S3 (o cualquier proveedor compatible -- MinIO,
Backblaze B2, Wasabi, Cloudflare R2...) vía `rclone`, con la misma
retención que el volumen local:

```bash
export WATCHGATE_BACKUP_S3_BUCKET="mi-bucket-de-backups"
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
# Solo si NO es AWS S3 real (MinIO, Backblaze, R2...):
export WATCHGATE_BACKUP_S3_ENDPOINT="https://s3.mi-proveedor.example"
export WATCHGATE_BACKUP_S3_REGION="auto"  # algunos proveedores S3-compatibles lo exigen así
```

```bash
# Restaurar desde S3 en vez de desde el volumen local:
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec postgres-backup \
  rclone copy "s3:mi-bucket-de-backups/watchgate-backups/watchgate-<timestamp>.sql.gz" /backups/
```

Requiere credenciales de un proveedor real -- no lo resuelve este repo
por su cuenta, solo automatiza la subida una vez las tienes.

## Variables de entorno

Ver `.env.example` para la lista completa y comentada. Resumen por bloque:

- **Capa semántica**: `WATCHGATE_LLM_PROVIDER`/`WATCHGATE_LLM_API_KEY` (o
  `WATCHGATE_LLM_BASE_URL` si `PROVIDER=local`, para un backend
  OpenAI-compatible propio -- Ollama, vLLM...).
- **Persistencia**: `WATCHGATE_DATABASE_URL` (Engine API, SQLModel) y
  `WATCHGATE_DASHBOARD_DATABASE_URL` (Dashboard, esquema aparte) -- ambas
  a Postgres en producción; sin ellas, SQLite local (un fichero por
  proceso, no compartido entre réplicas).
- **RAG distribuido** (opcional): `WATCHGATE_CHROMA_URL` apunta a un
  ChromaDB compartido entre despliegues en vez del índice local en disco.
  El feedback humano se aísla por `org_id` al consultar (ver
  `core/rag/retriever.py`); el corpus público de casos de ataque conocidos
  es intencionalmente compartido, nunca se filtra.
- **OAuth GitHub / OIDC**: opcional, solo si se quiere login federado en
  vez del login de desarrollo o usuario/contraseña local. Requiere un paso
  manual, una sola vez, en GitHub (no hay forma de automatizarlo desde
  este repo): *GitHub → Settings → Developer settings → OAuth Apps → New
  OAuth App*, con *Authorization callback URL* = el valor exacto de
  `WATCHGATE_GITHUB_REDIRECT_URI` (por defecto
  `http://localhost:8000/api/auth/github/callback`; en producción, la URL
  real del Dashboard). GitHub da el *Client ID* y genera el *Client
  Secret* ahí mismo -- van en `WATCHGATE_GITHUB_CLIENT_ID`/
  `WATCHGATE_GITHUB_CLIENT_SECRET`.

## Limitaciones conocidas, honestas

- Rate limiting de login: compartido entre réplicas si `WATCHGATE_REDIS_URL`
  está configurada (ver arriba); en memoria de proceso si no, que sigue
  siendo el default (no rompe nada para quien no lo necesita).
- Los dos esquemas (Engine DB y Dashboard) usan Alembic, pero con
  historiales de migración **separados** (ver "Migraciones de esquema"
  arriba) -- un cambio que toca ambos esquemas a la vez necesita dos
  migraciones y dos `upgrade head`, no uno solo.
- Backups de Postgres: automatizados (`postgres-backup` en
  `docker-compose.prod.yml`, ver arriba). Copia fuera de la máquina (S3 o
  compatible) disponible pero opcional vía `WATCHGATE_BACKUP_S3_BUCKET` --
  sin ella, el volumen local sigue siendo el único sitio con el backup.
- Logs estructurados (`WATCHGATE_LOG_FORMAT=json`) ya activos en
  producción, grepables/parseables por un agregador real si se conecta
  uno. Alerting proactivo (Sentry) opcional vía `WATCHGATE_SENTRY_DSN` --
  sin ella, sigue siendo cierto que nada avisa solo, hay que ir a mirar
  los logs a mano.
- Publicar en PyPI requiere antes decidir un nombre de paquete distinto
  (`watchgate` ya está registrado por un proyecto sin relación) -- no
  bloquea usar la GitHub Action (ver `action.yml`, se instala desde su
  propio checkout, no desde PyPI).
