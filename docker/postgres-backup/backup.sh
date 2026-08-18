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

# Copia fuera de la máquina (opcional): sin WATCHGATE_BACKUP_S3_BUCKET, el
# volumen local (postgres_backups) sigue siendo el único sitio con el
# backup -- protege de un error humano/de aplicación, pero no de perder la
# máquina entera (limitación documentada en docs/despliegue.md). Con la
# variable puesta, sube el fichero recién creado a un bucket S3 (o
# compatible) vía rclone -- RCLONE_CONFIG_S3_ENV_AUTH=true hace que rclone
# lea las credenciales de las variables estándar AWS_ACCESS_KEY_ID/
# AWS_SECRET_ACCESS_KEY/AWS_SESSION_TOKEN en vez de exigir un fichero de
# configuración propio montado aparte.
if [ -n "${WATCHGATE_BACKUP_S3_BUCKET:-}" ]; then
    S3_PREFIX="${WATCHGATE_BACKUP_S3_PREFIX:-watchgate-backups}"
    # "Minio" por defecto en cuanto hay un endpoint propio (nunca es AWS S3
    # real si se apunta a otro sitio) -- explícito en vez de dejar el
    # provider vacío: probado en vivo contra un MinIO real, sin esto rclone
    # avisa "s3 provider "" not known" (funciona igual por los defaults
    # genéricos, pero sin garantía de que siga siendo así para siempre).
    S3_PROVIDER="${WATCHGATE_BACKUP_S3_PROVIDER:-}"
    if [ -z "${S3_PROVIDER}" ]; then
        if [ -n "${WATCHGATE_BACKUP_S3_ENDPOINT:-}" ]; then
            S3_PROVIDER="Minio"
        else
            S3_PROVIDER="AWS"
        fi
    fi
    export RCLONE_CONFIG_S3_TYPE=s3
    export RCLONE_CONFIG_S3_ENV_AUTH=true
    export RCLONE_CONFIG_S3_PROVIDER="${S3_PROVIDER}"
    export RCLONE_CONFIG_S3_REGION="${WATCHGATE_BACKUP_S3_REGION:-us-east-1}"
    export RCLONE_CONFIG_S3_ENDPOINT="${WATCHGATE_BACKUP_S3_ENDPOINT:-}"

    echo "[backup] subiendo a s3://${WATCHGATE_BACKUP_S3_BUCKET}/${S3_PREFIX}/ (provider=${S3_PROVIDER})"
    rclone copyto "${OUT_FILE}" \
        "s3:${WATCHGATE_BACKUP_S3_BUCKET}/${S3_PREFIX}/$(basename "${OUT_FILE}")" \
        --s3-no-check-bucket
    echo "[backup] subida a S3 completada"

    # Misma retención que en local, aplicada también al bucket -- si no,
    # crece sin límite mientras el volumen local sí se poda.
    rclone delete "s3:${WATCHGATE_BACKUP_S3_BUCKET}/${S3_PREFIX}/" \
        --min-age "${RETENTION_DAYS}d" --include "watchgate-*.sql.gz"
    echo "[backup] retención aplicada en S3 (>${RETENTION_DAYS} días borrados)"
fi
