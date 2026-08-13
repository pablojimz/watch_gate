# Manual de Despliegue de Git Hooks (`pre-receive` server-side y `pre-push` client-side)

**WatchGate Git Server Hook Infrastructure**
**Ubicación**: `docs/manual_git_hooks.md`
**Fecha**: Agosto 2026

**Adenda 2026-08-11**: se añade la §5, un hook `pre-push` **client-side**
distinto del `pre-receive` documentado en §1-§4 -- corre en la máquina del
propio desarrollador, no en el servidor Git, y no usa el adaptador Python
`watchgate/adapters/git_hook/pre_receive.py` en absoluto (es un script bash
autocontenido, sin dependencia del paquete `watchgate`). Ver §5 para la
comparación completa entre ambos.

---

## 1. Introducción y Arquitectura

WatchGate proporciona un **Hook POSIX `pre-receive` Universal** (`watchgate/adapters/git_hook/pre_receive.py`) diseñado para ejecutarse en el servidor Git antes de aceptar cualquier `git push`. 

Este hook intercepta las propuestas de código en el servidor de control de versiones y consulta la **Engine API de WatchGate** o ejecuta el análisis local antes de que los commits se fusionen en la rama principal.

```
+------------------+         git push         +-------------------------------------+
|   Desarrollador  | -----------------------> |         Servidor Git / Bare         |
|   / Agente IA    |                          |  (GitLab, Bitbucket, Gitolite, SSH) |
+------------------+                          +------------------+------------------+
                                                                 |
                                                  Ejecuta hooks/pre-receive
                                                                 |
                                                                 v
                                              +-------------------------------------+
                                              | watchgate/adapters/git_hook/        |
                                              |           pre_receive.py            |
                                              +------------------+------------------+
                                                                 |
                                                  Petición HTTP / API (< 8s)
                                                                 |
                                                                 v
                                              +-------------------------------------+
                                              |       Engine API / WatchGate        |
                                              +------------------+------------------+
                                                                 |
                                                       Evalúa Semáforo
                                                                 |
                        +----------------------------------------+----------------------------------------+
                        |                                                                                 |
                 Semáforo VERDE / AMARILLO                                                          Semáforo ROJO
                        |                                                                                 |
                        v                                                                                 v
             [Exit Code 0: Push Aceptado]                                                  [Exit Code 1: Push Rechazado]
                                                                                           Imprime alertas en stderr
```

---

## 2. Características Clave del Hook `pre-receive`

1. **Soporte POSIX Estándar**: Ejecutable sin dependencias pesadas en el servidor Git.
2. **Manejo Explícito de SHA Nulo (`0000000000000000000000000000000000000000`)**:
   * En creaciones de ramas nuevas o puestas iniciales (`old-sha == 00*40`), extrae el diff utilizando `git diff-tree -p <new-sha>` en lugar de `git diff <old> <new>` para prevenir fallos catastróficos de Git.
   * En borrados de ramas (`new-sha == 00*40`), ignora la verificación y permite la operación de borrado inmediatamente.
3. **Control Estricto de Latencia (Timeout < 8s)**:
   * Aplica un timeout estricto de 8 segundos en la comunicación HTTP con la Engine API para evitar que la terminal del desarrollador se bloquee.
4. **Política de Contingencia Cero-Bloqueo o Fail-Closed**:
   * Ante caídas de red o errores de infraestructura de la API, aplica la política configurada por la organización (`fail_closed=True` o `fail_closed=False`).

---

## 3. Guía de Instalación por Entorno Git Server

### 3.1 Servidor Git Bare Estándar (SSH)

En un repositorio Git Bare en el servidor (`/srv/git/mi-proyecto.git`):

1. Copia el ejecutable del hook a la carpeta `hooks/`:

```bash
cp /ruta/a/watchgate/adapters/git_hook/pre_receive.py /srv/git/mi-proyecto.git/hooks/pre-receive
chmod +x /srv/git/mi-proyecto.git/hooks/pre-receive
```

2. Configura las variables de entorno para el hook en el servidor:

```bash
export WATCHGATE_API_URL="http://watchgate-engine.internal/api/v1/analyze"
export WATCHGATE_API_KEY="wg_live_4a8f9c2d..."
```

---

### 3.2 GitLab Self-Managed (Custom Hooks / Server Hooks)

En GitLab Self-Managed, los hooks de servidor se configuran como **Custom Hooks**:

1. Accede al directorio de almacenamiento del repositorio en el servidor GitLab (ej: `/var/opt/gitlab/git-data/repositories/@hashed/.../proyecto.git`).
2. Crea el directorio `custom_hooks`:

```bash
mkdir -p custom_hooks
```

3. Copia el hook `pre-receive`:

```bash
cp /ruta/a/watchgate/adapters/git_hook/pre_receive.py custom_hooks/pre-receive
chmod +x custom_hooks/pre-receive
chown -R git:git custom_hooks
```

---

### 3.3 Bitbucket Data Center / Server

En Atlassian Bitbucket Server:

1. Utiliza la funcionalidad **External Hooks Plugin** o instala el hook directamente en el directorio del repositorio en disco (`<BITBUCKET_HOME>/shared/data/repositories/<REPO_ID>/subhooks/pre-receive`).
2. Alternativamente, crea un script ejecutable wrapper en el sistema que invoque Python:

```bash
#!/bin/bash
export WATCHGATE_API_URL="http://watchgate.internal/api/v1/analyze"
export WATCHGATE_API_KEY="wg_live_..."
exec python3 /opt/watchgate/adapters/git_hook/pre_receive.py "$@"
```

---

### 3.4 Gitolite

En un servidor administrado con Gitolite:

1. Copia el hook al directorio de hooks comunes de Gitolite:

```bash
cp /ruta/a/watchgate/adapters/git_hook/pre_receive.py ~/.gitolite/hooks/common/pre-receive
chmod +x ~/.gitolite/hooks/common/pre-receive
gitolite setup --hooks
```

---

## 4. Pruebas de Funcionamiento

Para verificar el comportamiento del hook localmente sin realizar un push real, simula la entrada estándar enviando los parámetros de ref:

```bash
echo "4b825dc642cb6eb9a060e54bf8d69288fbee4904 e69de29bb2d1d6434b8b29ae775ad8c2e48c5391 refs/heads/main" | python3 watchgate/adapters/git_hook/pre_receive.py
```

Si el código contiene patrones de alto riesgo y `block_on_red: true`, el comando terminará con **Exit Code 1** imprimiendo las razones en `stderr`:

```
========================================================================
[BLOQUEADO POR WATCHGATE] Push rechazado por políticas de seguridad
========================================================================
Puntuación de Riesgo: 85/100 (Semáforo: ROJO)

Hallazgos Críticos:
  - [ESTÁTICA] eval-exec-dynamic: Uso peligroso de eval() detectado en src/auth.py
========================================================================
```

---

## 5. Hook Client-Side `pre-push` (alternativa ligera, sin servidor)

### 5.1 Qué es y en qué se diferencia de `pre-receive`

Mientras que `pre-receive` (§1-§4) corre en el **servidor Git** después de
que el push ya salió de la máquina del desarrollador, este hook corre
**antes**, en el propio `.git/hooks/` local del repositorio que se está
desarrollando -- feedback inmediato en la terminal del propio desarrollador,
sin depender de que exista un servidor Git con hooks instalados.

No es una envoltura de `watchgate/adapters/git_hook/pre_receive.py` ni de
ningún otro módulo del paquete Python `watchgate` -- es un script bash
autocontenido (`git`+`curl`+`jq`, sin instalar nada de Python), que llama
directamente a `POST /api/v1/analyze` del Engine API, con la misma lógica
de cálculo de diff (`git merge-base` + `git diff -U3`) que usa
`entrypoint.sh` (la GitHub Action, ver `docs/progreso/progreso_Pablo_Jiménez_Castro.md`
§2.6) -- son dos clientes distintos del mismo Engine API, para dos momentos
distintos del ciclo de vida de un cambio.

```
+------------------+   git push   +---------------------------+
|   Desarrollador   | -----------> |  .git/hooks/pre-push       |
|  (su propia       |              |  (local, en su máquina --  |
|   máquina)        |              |   NO en el servidor Git)   |
+------------------+              +--------------+--------------+
                                                  |
                                     git merge-base + git diff -U3
                                     (contra WATCHGATE_BASE_REF)
                                                  |
                                                  v
                                   POST /api/v1/analyze (Engine API)
                                   Authorization: Bearer $WATCHGATE_ENGINE_API_KEY
                                                  |
                                                  v
                                         Score + hallazgos
                                                  |
                        +--------------------------+--------------------------+
                        |                                                     |
              score < WATCHGATE_RISK_THRESHOLD                  score >= WATCHGATE_RISK_THRESHOLD
                        |                                                     |
                        v                                                     v
              [Exit 0: push continúa]                          [Exit 1 si BLOCK_ON_RISK=1: push
                                                                  rechazado localmente, antes de
                                                                  llegar siquiera al servidor]
```

| | `pre-receive` (§1-§4) | `pre-push` (esta sección) |
|---|---|---|
| Dónde corre | Servidor Git (bare repo) | Máquina del desarrollador |
| Cuándo | El push ya salió, llega al servidor | Antes de que el push salga de la máquina |
| Implementación | `watchgate/adapters/git_hook/pre_receive.py` (Python) | Script bash independiente, sin Python |
| Ante fallo de infraestructura | Configurable (`fail_closed` true/false) | Siempre "fail open" -- deja pasar el push con aviso, nunca bloquea por un problema de red/Engine API caído |
| Instalación | Una vez, por el administrador del servidor Git (§3) | Una vez, por cada desarrollador, en su propio checkout local |
| Se puede saltar | No (el servidor lo hace cumplir) | Sí, con `git push --no-verify` -- es una ayuda local, no una barrera de seguridad real |

**Importante**: este hook **no sustituye ningún control real** -- es
"fail open" por diseño (si el Engine API no responde, dice
`echo "... se deja pasar el push sin analizar."` y sale con código 0). El
control que de verdad protege el repositorio sigue siendo, según el
contexto: `pre-receive` en el servidor (§1-§4) para un servidor Git propio,
o la GitHub Action + Check Run (`action.yml`/`entrypoint.sh`, ver
`docs/progreso/progreso_Pablo_Jiménez_Castro.md` §2.6) para un repo alojado
en GitHub -- ese sí usa credenciales gestionadas centralmente (secrets de
GitHub) y no se puede saltar con un flag local.

### 5.2 El script completo

Ubicación real, tal como está instalado hoy: `.git/hooks/pre-push`, dentro
de cada checkout local donde se quiera activar (no es parte del repo
`watch_gate` en sí -- `.git/hooks/` nunca se versiona con git, es
puramente local a cada máquina).

```bash
#!/usr/bin/env bash
# Git hook pre-push: analiza el diff entre WATCHGATE_BASE_REF y HEAD contra
# el WatchGate Engine API local, antes de dejar completar el push.
#
# A diferencia de entrypoint.sh (pensado para GitHub Actions): NO intenta
# publicar ningún Check Run -- no hay PR real al que publicarlo en un push
# local -- y no depende de `act` ni de ningún contenedor extra que simule
# un runner, solo git+curl+jq directos contra el Engine API ya levantado
# (docker compose up -d postgres engine-api, desde el repo watch_gate).
#
# Configuración vía variables de entorno (todas opcionales salvo la key):
#   WATCHGATE_ENGINE_API_URL   (default: http://localhost:8080)
#   WATCHGATE_ENGINE_API_KEY   (obligatoria -- export la variable antes de
#                                hacer push, no la hardcodees aquí)
#   WATCHGATE_BASE_REF         (default: main)
#   WATCHGATE_RISK_THRESHOLD   (default: 70)
#   WATCHGATE_BLOCK_ON_RISK    (default: 1 -- con 0, nunca bloquea el push,
#                                solo informa)
#
# Filosofía "fail open", al revés que entrypoint.sh (que falla cerrado a
# propósito en CI): cualquier problema de infraestructura (Engine API
# caído, sin red, respuesta rara) deja pasar el push igualmente con un
# aviso -- lo único que bloquea de verdad es un score real por encima del
# umbral. En CI un fallo de infraestructura debe ser visible y bloquear;
# en un hook local, bloquear cada push porque el Engine API no está
# levantado en ese momento sería más ruido que ayuda.
set -euo pipefail

: "${WATCHGATE_ENGINE_API_URL:=http://localhost:8080}"
: "${WATCHGATE_ENGINE_API_KEY:?Falta WATCHGATE_ENGINE_API_KEY -- exporta la variable antes de hacer push.}"
: "${WATCHGATE_BASE_REF:=main}"
: "${WATCHGATE_RISK_THRESHOLD:=70}"
: "${WATCHGATE_BLOCK_ON_RISK:=1}"

engine_api_url="${WATCHGATE_ENGINE_API_URL%/}"

# Drenar stdin -- git pasa aquí la lista de refs a pushear
# (<local ref> <local sha1> <remote ref> <remote sha1>), pero este hook
# simplificado no la necesita: siempre compara HEAD contra
# WATCHGATE_BASE_REF, igual que hace entrypoint.sh con `base-ref`.
cat >/dev/null

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

head_sha="$(git rev-parse HEAD)"
base_sha="$(git merge-base "$WATCHGATE_BASE_REF" HEAD 2>/dev/null)" || {
    echo "[WatchGate] No se pudo calcular merge-base contra '$WATCHGATE_BASE_REF' -- se omite el análisis." >&2
    exit 0
}

if [ "$base_sha" = "$head_sha" ]; then
    echo "[WatchGate] Sin cambios respecto a '$WATCHGATE_BASE_REF' -- nada que analizar."
    exit 0
fi

diff_file="$workdir/diff.patch"
git diff -U3 "$base_sha" "$head_sha" > "$diff_file"

if [ ! -s "$diff_file" ]; then
    echo "[WatchGate] Diff vacío -- nada que analizar."
    exit 0
fi

payload_file="$workdir/payload.json"
jq -n \
    --rawfile diff_text "$diff_file" \
    --arg base_sha "$base_sha" \
    --arg head_sha "$head_sha" \
    --arg repo "$(basename "$(git rev-parse --show-toplevel)")" \
    '{
        diff_text: $diff_text,
        base_sha: $base_sha,
        head_sha: $head_sha,
        repo_path: ".",
        metadata: { repo: $repo, pr_id: "local-push" }
    }' > "$payload_file"

echo "[WatchGate] Analizando cambios ($WATCHGATE_BASE_REF..$(git rev-parse --short HEAD)) contra $engine_api_url ..."

response_file="$workdir/response.json"
http_code="$(curl -sS -o "$response_file" -w '%{http_code}' \
    --max-time 120 \
    -X POST "$engine_api_url/api/v1/analyze" \
    -H "Authorization: Bearer $WATCHGATE_ENGINE_API_KEY" \
    -H "Content-Type: application/json" \
    --data @"$payload_file")" || {
    echo "[WatchGate] No se pudo contactar con el Engine API ($engine_api_url) -- ¿está levantado? Se deja pasar el push sin analizar." >&2
    exit 0
}

if [ "$http_code" -lt 200 ] || [ "$http_code" -ge 300 ]; then
    echo "[WatchGate] Engine API devolvió HTTP $http_code -- se deja pasar el push sin bloquear. Respuesta: $(cat "$response_file")" >&2
    exit 0
fi

score="$(jq -r '.score // empty' "$response_file")"
if [ -z "$score" ] || ! [[ "$score" =~ ^[0-9]+$ ]]; then
    echo "[WatchGate] Respuesta sin 'score' numérico válido -- se deja pasar el push. Respuesta: $(cat "$response_file")" >&2
    exit 0
fi

echo ""
echo "[WatchGate] Score: $score/100 (umbral: $WATCHGATE_RISK_THRESHOLD)"
jq -r '
  (.layer_results // {}) | to_entries[] |
  select(.value.skipped == false and (.value.findings | length) > 0) |
  .value.findings[] |
  "  - [\(.severity)] \(.file_path):\(.line // "?") -- \(.rule_id)"
' "$response_file"
echo ""

if [ "$score" -ge "$WATCHGATE_RISK_THRESHOLD" ]; then
    echo "[WatchGate] Score $score >= umbral $WATCHGATE_RISK_THRESHOLD." >&2
    if [ "$WATCHGATE_BLOCK_ON_RISK" = "1" ]; then
        echo "[WatchGate] Push BLOQUEADO (WATCHGATE_BLOCK_ON_RISK=1). Usa 'git push --no-verify' para saltarte este hook si hace falta." >&2
        exit 1
    fi
    echo "[WatchGate] WATCHGATE_BLOCK_ON_RISK=0 -- se deja pasar igualmente." >&2
fi

exit 0
```

### 5.3 Instalación paso a paso

1. Levanta el Engine API en local (desde el repo `watch_gate`):

```bash
docker compose up -d postgres engine-api
```

2. Provisiona una API Key de prueba (una sola vez -- queda en el volumen
   `postgres_data`, sobrevive a `docker compose down`/`up` sin `-v`):

```bash
docker compose exec engine-api python3 -c "
from watchgate.db.connection import get_session
from watchgate.db.repository import create_organization, create_user, create_api_key
with next(get_session()) as session:
    org = create_organization(session, name='Test', org_id='local-test')
    user = create_user(session, email='test@local', name='Test', org_id=org.id)
    _, token = create_api_key(session, user_id=user.id, org_id=org.id, monitored_repo_id='local-repo')
    print(token)
"
```

3. Copia el script de §5.2 a `<tu-repo>/.git/hooks/pre-push` y márcalo
   ejecutable:

```bash
chmod +x .git/hooks/pre-push
```

4. Antes de cada `git push`, exporta la API Key (no hardcodeada en el
   script -- ver §5.1, es deliberado):

```bash
export WATCHGATE_ENGINE_API_KEY="wg_live_..."
git push origin <tu-rama>
```

### 5.4 Cómo está montado en el repo de prueba (`prueba_1`)

Instalación real, verificada, en `C:\Users\pasbl\Documents\repos_prueba\prueba_1`:

```
prueba_1/
├── .git/
│   └── hooks/
│       └── pre-push          # el script de §5.2, chmod +x, NO versionado
├── .github/
│   └── workflows/
│       └── watchgate.yml     # copia del workflow de watch_gate (uses: ./)
├── action.yml                # copia de la Action de watch_gate
├── entrypoint.sh             # copia del entrypoint.sh de watch_gate
├── act_pr_event.json         # evento pull_request sintético para `act`
├── event.json
├── config.py                 # fixture: clave AWS hardcodeada (AKIA...)
├── handler.py                # fixture: os.system() con concatenación
└── README.md
```

`origin` apunta al propio directorio local (`git remote -v` → `origin .`),
así que no hace falta ningún repositorio remoto real para probar el hook
-- `git push origin <rama>` funciona contra sí mismo, y el hook `pre-push`
se dispara igual que lo haría contra un remote de verdad, porque
`pre-push` se ejecuta **antes** de que git decida a dónde manda los datos.

Dos ramas relevantes:

* `main` (806adfd) -- estado base, sin hallazgos.
* `feature/test-finding` (c935379, 4f57652) -- dos commits de prueba con
  vulnerabilidades deliberadas (clave AWS hardcodeada, inyección de
  comandos vía `os.system`), usados para verificar que el hook detecta
  algo real, no solo que no revienta.

**Verificado en vivo** (no solo instalado): un `git push origin
feature/test-finding` desde este repo, con la API Key exportada, dispara
el hook, calcula el diff `main..feature/test-finding`, llama al Engine API
real, y devuelve `score=33` con el hallazgo real de
`hardcoded-aws-access-key` sobre `config.py:9` impreso en la terminal antes
de que el push complete.
