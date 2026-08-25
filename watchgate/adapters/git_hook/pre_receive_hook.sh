#!/usr/bin/env bash
# Hook `pre-receive` server-side para servidores Git tipo GitLab
# self-managed, Gitea/Forgejo, Bitbucket Server, Gitolite o bare SSH: se
# instala en <repo>.git/hooks/pre-receive.d/watchgate (o directo como
# hooks/pre-receive en un bare SSH sin soporte de *.d/) y llama al Engine
# API real de WatchGate por HTTP -- a diferencia de
# watchgate/adapters/git_hook/pre_receive.py (que analiza en proceso,
# importando el paquete `watchgate`, y por tanto exige tenerlo instalado en
# el propio servidor Git), este script solo necesita `git`+`curl`+`jq`.
#
# Este es el ÚNICO fichero fuente -- vive dentro del paquete `watchgate`
# (no en docker/) precisamente para poder distribuirse por HTTP sin
# necesitar el repo `watch_gate` clonado en el servidor Git de destino: el
# Engine API lo sirve tal cual en `GET /api/v1/hooks/pre-receive` (ver
# watchgate/api/routers/hooks.py), así que instalarlo en un servidor real
# es un solo `curl` -- ver docs/manual_git_hooks.md §6.3.
# `docker/git-server-hooks/install.sh` (para el Forgejo local de pruebas de
# docker-compose.gitserver.yml) copia este mismo fichero.
#
# Mismo patrón que el hook `pre-push` client-side documentado en
# docs/manual_git_hooks.md §5.2, pero para el protocolo `pre-receive`
# (múltiples refs por stdin, no un solo HEAD) y FAIL-CLOSED por defecto
# -- este es el control real del servidor, no una ayuda local que se pueda
# saltar con --no-verify.
#
# Configuración vía variables de entorno:
#   WATCHGATE_ENGINE_API_URL   (default: http://engine-api:8080 -- nombre
#                                del servicio en la red de Docker Compose)
#   WATCHGATE_ENGINE_API_KEY   (obligatoria -- ver provision_repo.sh)
#   WATCHGATE_FAIL_CLOSED      (default: 1 -- con 0, un fallo de
#                                infraestructura deja pasar el push)
#   WATCHGATE_HOOK_TIMEOUT     (default: 240 -- con un LLM LOCAL vía Ollama
#                                de WATCHGATE_LLM_PROVIDER=local, verificado
#                                en vivo: un modelo "thinking" de 27B tarda
#                                >60s en un diff real incluso con GPU A100,
#                                muy por encima del límite pensado para un
#                                LLM en la nube. Con proveedor en la nube
#                                (Anthropic/Gemini) 60s suele bastar -- baja
#                                este valor si es tu caso.)
set -uo pipefail

# install.sh escribe la API key de este repo en hooks/watchgate.env (NO en
# este script, que es el mismo fichero para todos los repos) -- se sourcea
# aquí si existe. Sin `set -e`, un fichero ausente solo imprime un aviso y
# sigue: el chequeo de WATCHGATE_ENGINE_API_KEY más abajo ya cubre ese caso
# con fail-closed.
hook_env_file="$(dirname "$0")/../watchgate.env"
[ -f "$hook_env_file" ] && . "$hook_env_file"

: "${WATCHGATE_ENGINE_API_URL:=http://engine-api:8080}"
: "${WATCHGATE_FAIL_CLOSED:=1}"
: "${WATCHGATE_HOOK_TIMEOUT:=240}"

engine_api_url="${WATCHGATE_ENGINE_API_URL%/}"
empty_tree_sha="4b825dc642cb6eb9a060e54bf8d69288fbee4904"

# `hooks/pre-receive.d/watchgate` corre con cwd = la raíz del repo bare
# (p.ej. /data/git/repositories/testadmin/test-repo.git) -- de ahí se
# deriva el nombre visible del repo sin depender de variables de entorno
# específicas de Forgejo, que este hook (a diferencia del `gitea hook`
# interno) no recibe.
repo_dir="$(pwd)"
repo_name="$(basename "$repo_dir" .git)"
owner_name="$(basename "$(dirname "$repo_dir")")"
repo_full_name="${owner_name}/${repo_name}"

if [ -z "${WATCHGATE_ENGINE_API_KEY:-}" ]; then
    echo "[WatchGate] WATCHGATE_ENGINE_API_KEY no configurada para ${repo_full_name} -- push rechazado (fail-closed)." >&2
    exit 1
fi

overall_blocked=0

# Git pasa por stdin una línea `<old_sha> <new_sha> <ref_name>` por cada
# ref que se está actualizando en este push.
while read -r old_sha new_sha ref_name; do
    [ -z "${old_sha:-}" ] && continue

    if [ "${new_sha//0/}" = "" ]; then
        # Borrado de rama/tag: nada que analizar.
        continue
    fi

    if [ "${old_sha//0/}" = "" ]; then
        base_ref="$empty_tree_sha"
    else
        base_ref="$old_sha"
    fi

    diff_text="$(git diff "$base_ref" "$new_sha" 2>/dev/null)"
    if [ -z "$diff_text" ]; then
        continue
    fi

    workdir="$(mktemp -d)"
    payload_file="$workdir/payload.json"
    response_file="$workdir/response.json"

    jq -n \
        --arg diff_text "$diff_text" \
        --arg base_sha "$old_sha" \
        --arg head_sha "$new_sha" \
        --arg repo "$repo_full_name" \
        --arg ref_name "$ref_name" \
        '{
            diff_text: $diff_text,
            base_sha: $base_sha,
            head_sha: $head_sha,
            repo_path: $repo,
            metadata: { repo: $repo, ref_name: $ref_name, pr_id: $ref_name }
        }' > "$payload_file"

    echo "[WatchGate] Analizando ${ref_name} (${repo_full_name}) contra ${engine_api_url} ..."

    http_code="$(curl -sS -o "$response_file" -w '%{http_code}' \
        --max-time "$WATCHGATE_HOOK_TIMEOUT" \
        -X POST "$engine_api_url/api/v1/analyze" \
        -H "Authorization: Bearer $WATCHGATE_ENGINE_API_KEY" \
        -H "Content-Type: application/json" \
        --data @"$payload_file")"
    curl_exit=$?

    if [ $curl_exit -ne 0 ] || [ "$http_code" -lt 200 ] || [ "$http_code" -ge 300 ]; then
        echo "[WatchGate] No se pudo obtener un análisis válido de ${engine_api_url} (HTTP ${http_code:-?}): $(cat "$response_file" 2>/dev/null)" >&2
        rm -rf "$workdir"
        if [ "$WATCHGATE_FAIL_CLOSED" = "1" ]; then
            echo "[WatchGate] Política FAIL_CLOSED activa: push rechazado por fallo de infraestructura." >&2
            exit 1
        fi
        continue
    fi

    score="$(jq -r '.score // empty' "$response_file")"
    semaforo="$(jq -r '.semaforo // empty' "$response_file")"
    rm -rf "$workdir"

    if [ -z "$score" ]; then
        echo "[WatchGate] Respuesta sin score válido -- push rechazado (fail-closed)." >&2
        [ "$WATCHGATE_FAIL_CLOSED" = "1" ] && exit 1
        continue
    fi

    if [ "$semaforo" = "rojo" ] || [ "$semaforo" = "ROJO" ]; then
        overall_blocked=1
        echo "" >&2
        echo "❌ [WatchGate] PUSH RECHAZADO (${ref_name}): score ${score}/100 [SEMÁFORO ROJO]" >&2
        echo "   Corrija los hallazgos de seguridad antes de reintentar el git push." >&2
        echo "" >&2
    else
        echo "✅ [WatchGate] PUSH APROBADO (${ref_name}): ${semaforo} (${score}/100)"
    fi
done

exit $overall_blocked
