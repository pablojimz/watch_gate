#!/usr/bin/env bash
# conectar_resto_dashboard.sh
#
# Lanza conectar_resto_dashboard.py DENTRO del contenedor
# dashboard-worker: conecta en el Dashboard (modo "auditado") todos los
# repos de top-100-github-links.txt que aun no esten monitorizados, y
# encola sus PRs abiertas -- ver el docstring de ese .py para el detalle
# completo (coste/tiempo esperado, que hace exactamente, como cambiar la
# organizacion de destino).
#
# Requiere que el stack de docker compose (watch_gate-dashboard-worker-1,
# postgres, redis) ya este arriba -- no lo levanta el.
#
# USO:
#   ./conectar_resto_dashboard.sh
#
# VARIABLES DE ENTORNO (opcionales, pasan directas al script Python):
#   WATCHGATE_BULK_ORG_ID      Organizacion del Dashboard a la que conectar
#                              los repos nuevos (default: la organizacion
#                              "admin (personal)" activa al escribir esto).
#   WATCHGATE_BULK_USER_LOGIN  Usuario al que asignar el rol de mantenedor
#                              de cada repo nuevo (default: "admin").
#   WORKER_CONTAINER           Nombre del contenedor worker (default:
#                              watch_gate-dashboard-worker-1).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_CONTAINER="${WORKER_CONTAINER:-watch_gate-dashboard-worker-1}"

if ! docker ps --format '{{.Names}}' | grep -qx "$WORKER_CONTAINER"; then
    echo "ERROR: el contenedor '$WORKER_CONTAINER' no está arriba (docker compose up -d)." >&2
    exit 1
fi

echo "[conectar_resto] Copiando script y listado de repos al contenedor..." >&2
docker cp "$SCRIPT_DIR/conectar_resto_dashboard.py" "$WORKER_CONTAINER:/tmp/conectar_resto_dashboard.py"
docker cp "$SCRIPT_DIR/top-100-github-links.txt" "$WORKER_CONTAINER:/tmp/top-100-github-links.txt"

echo "[conectar_resto] Ejecutando dentro del contenedor (org=${WATCHGATE_BULK_ORG_ID:-<default del script>})..." >&2
docker exec \
    -e "WATCHGATE_BULK_ORG_ID=${WATCHGATE_BULK_ORG_ID:-}" \
    -e "WATCHGATE_BULK_USER_LOGIN=${WATCHGATE_BULK_USER_LOGIN:-}" \
    "$WORKER_CONTAINER" \
    python3 /tmp/conectar_resto_dashboard.py /tmp/top-100-github-links.txt
