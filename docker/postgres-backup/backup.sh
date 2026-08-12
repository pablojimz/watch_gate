#!/bin/sh
# backup.sh — vuelca TODO el cluster Postgres (las dos bases,
# `watchgate` y `watchgate_dashboard`, más roles) a un único fichero
# comprimido. `pg_dumpall` en vez de `pg_dump` por base por separado a
# propósito: es un solo comando para las dos bases que conviven en el
# mismo servidor Postgres del propio docker-compose.yml (ver
# docker/postgres-init/01-create-dashboard-db.sql para el porqué de que
# sean dos bases distintas), y de paso incluye los roles -- una
# restauración desde este fichero no depende de que alguien recuerde
# recrear el usuario `watchgate` a mano primero.
#
# Falla cerrado: `set -e` -- si `pg_dumpall` falla a mitad (p. ej. Postgres
# no está listo todavía), el script para en vez de dejar un .sql.gz vacío
# o truncado que parece un backup válido hasta que hace falta restaurarlo.
set -eu

BACKUP_DIR="${WATCHGATE_BACKUP_DIR:-/backups}"
RETENTION_DAYS="${WATCHGATE_BACKUP_RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="${BACKUP_DIR}/watchgate-${TIMESTAMP}.sql.gz"
TMP_FILE="${OUT_FILE}.tmp"

mkdir -p "${BACKUP_DIR}"

echo "[backup] $(date -u +%Y-%m-%dT%H:%M:%SZ) iniciando pg_dumpall -> ${OUT_FILE}"

# A fichero temporal primero y `mv` al final -- si el propio proceso se
# interrumpe (contenedor parado a mitad, disco lleno), no queda un
# `watchgate-<timestamp>.sql.gz` truncado con nombre de backup "real" que
# la rotación de abajo trataría como válido.
pg_dumpall -h "${PGHOST:-postgres}" -U "${PGUSER:-watchgate}" | gzip > "${TMP_FILE}"
mv "${TMP_FILE}" "${OUT_FILE}"

echo "[backup] completado: $(du -h "${OUT_FILE}" | cut -f1)"

# Rotación: solo borra sus propios ficheros (watchgate-*.sql.gz), nunca
# barre el directorio entero -- por si algún día se monta el mismo volumen
# para algo más.
find "${BACKUP_DIR}" -maxdepth 1 -name 'watchgate-*.sql.gz' -mtime "+${RETENTION_DAYS}" -print -delete

echo "[backup] retención aplicada (>${RETENTION_DAYS} días borrados)"
