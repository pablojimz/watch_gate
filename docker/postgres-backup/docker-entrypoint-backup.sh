#!/bin/sh
# Entrypoint: escribe el crontab con la variables de entorno del propio
# contenedor ya resueltas (crond no las hereda de por sí -- ver Dockerfile)
# y arranca crond en primer plano.
set -eu

CRON_SCHEDULE="${WATCHGATE_BACKUP_CRON:-0 3 * * *}"

{
    echo "PGPASSWORD=${PGPASSWORD:-}"
    echo "PGHOST=${PGHOST:-postgres}"
    echo "PGUSER=${PGUSER:-watchgate}"
    echo "WATCHGATE_BACKUP_DIR=${WATCHGATE_BACKUP_DIR:-/backups}"
    echo "WATCHGATE_BACKUP_RETENTION_DAYS=${WATCHGATE_BACKUP_RETENTION_DAYS:-14}"
    # Copia a S3 opcional (ver backup.sh) -- mismo motivo que las de arriba:
    # crond no hereda ninguna variable de entorno del contenedor por su
    # cuenta, así que sin volcarlas aquí también, el backup del cron
    # correría sin credenciales aunque el backup inicial de más abajo
    # (mismo proceso que este script, sí las hereda) funcionase bien.
    echo "WATCHGATE_BACKUP_S3_BUCKET=${WATCHGATE_BACKUP_S3_BUCKET:-}"
    echo "WATCHGATE_BACKUP_S3_PREFIX=${WATCHGATE_BACKUP_S3_PREFIX:-}"
    echo "WATCHGATE_BACKUP_S3_REGION=${WATCHGATE_BACKUP_S3_REGION:-}"
    echo "WATCHGATE_BACKUP_S3_ENDPOINT=${WATCHGATE_BACKUP_S3_ENDPOINT:-}"
    echo "WATCHGATE_BACKUP_S3_PROVIDER=${WATCHGATE_BACKUP_S3_PROVIDER:-}"
    echo "AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-}"
    echo "AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}"
    echo "AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN:-}"
    echo "${CRON_SCHEDULE} /usr/local/bin/backup.sh >> /proc/1/fd/1 2>&1"
} > /etc/crontabs/root

echo "[entrypoint] backup programado: '${CRON_SCHEDULE}' (UTC)"

# Backup inicial al arrancar el contenedor -- si alguien despliega hoy, no
# espera hasta las 03:00 para tener el primer backup real.
/usr/local/bin/backup.sh || echo "[entrypoint] backup inicial falló, crond seguirá reintentando según lo programado"

exec crond -f -l 2
