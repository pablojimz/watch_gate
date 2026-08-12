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
    echo "${CRON_SCHEDULE} /usr/local/bin/backup.sh >> /proc/1/fd/1 2>&1"
} > /etc/crontabs/root

echo "[entrypoint] backup programado: '${CRON_SCHEDULE}' (UTC)"

# Backup inicial al arrancar el contenedor -- si alguien despliega hoy, no
# espera hasta las 03:00 para tener el primer backup real.
/usr/local/bin/backup.sh || echo "[entrypoint] backup inicial falló, crond seguirá reintentando según lo programado"

exec crond -f -l 2
