#!/usr/bin/env bash
# Sube un snapshot completo del repo (vía `git archive`) al Engine API
# para construir su mapa de conocimiento -- ver
# watchgate/api/routers/hooks.py::upload_repo_snapshot y
# watchgate/core/repo_graph.py (el pipeline que procesa lo que llega aquí).
#
# A diferencia del hook `pre-receive` (que corre en CADA push, solo con el
# diff), este script lo ejecuta el administrador del servidor Git A MANO:
# una vez al instalar el hook, y de nuevo cuando quiera refrescar el mapa
# tras cambios grandes -- no hay repolling automático, mismo criterio que
# el resto de escaneos de WatchGate (ver
# watchgate/service/repo_polling.py).
#
# Uso, desde DENTRO del repo (bare o con working tree), en el propio
# servidor Git:
#   export WATCHGATE_ENGINE_API_URL="http://tu-engine-api:8080"
#   export WATCHGATE_ENGINE_API_KEY="wg_live_..."
#   /ruta/a/upload_snapshot.sh [ref]
#
# [ref] por defecto es HEAD. Si el hook ya está instalado en este repo
# (ver install.sh / la §6.3 del manual), las mismas variables ya viven en
# hooks/watchgate.env -- este script las sourcea automáticamente si las
# encuentra ahí y no están ya exportadas.
set -euo pipefail

ref="${1:-HEAD}"

# Mismo fichero que sourcea el propio hook (ver pre_receive_hook.sh) --
# reutilizar la config ya instalada en vez de pedir que se repita a mano.
hook_env_file="./hooks/watchgate.env"
if [ -z "${WATCHGATE_ENGINE_API_KEY:-}" ] && [ -f "$hook_env_file" ]; then
    # shellcheck disable=SC1090
    . "$hook_env_file"
fi

: "${WATCHGATE_ENGINE_API_URL:?Falta WATCHGATE_ENGINE_API_URL -- exporta la variable, o ejecuta esto desde el repo con el hook ya instalado.}"
: "${WATCHGATE_ENGINE_API_KEY:?Falta WATCHGATE_ENGINE_API_KEY -- exporta la variable, o ejecuta esto desde el repo con el hook ya instalado.}"

engine_api_url="${WATCHGATE_ENGINE_API_URL%/}"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
snapshot_file="$workdir/snapshot.tar"

echo "[WatchGate] Empaquetando ${ref} con git archive..."
git archive --format=tar --output="$snapshot_file" "$ref"

size_bytes="$(wc -c < "$snapshot_file")"
echo "[WatchGate] Snapshot: $((size_bytes / 1024 / 1024)) MB -- subiendo a ${engine_api_url}/api/v1/hooks/repo-snapshot ..."

http_code="$(curl -sS -o "$workdir/response.json" -w '%{http_code}' \
    --max-time 300 \
    -X POST "$engine_api_url/api/v1/hooks/repo-snapshot" \
    -H "Authorization: Bearer $WATCHGATE_ENGINE_API_KEY" \
    -F "snapshot=@${snapshot_file};type=application/x-tar")"

if [ "$http_code" -lt 200 ] || [ "$http_code" -ge 300 ]; then
    echo "[WatchGate] Fallo subiendo el snapshot (HTTP ${http_code}): $(cat "$workdir/response.json")" >&2
    exit 1
fi

echo "[WatchGate] Snapshot aceptado -- el mapa de conocimiento se está construyendo en segundo plano."
cat "$workdir/response.json"
echo
