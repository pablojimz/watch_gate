# Backup programado del Postgres de docker-compose.prod.yml -- pg_dumpall
# diario (hora configurable) a un volumen local, con rotación. Basado en la
# propia imagen postgres:16-alpine (misma versión que el servidor real, así
# pg_dumpall/pg_dump siempre coinciden en versión con lo que están
# volcando) en vez de una imagen de terceros -- ya trae pg_dumpall y
# crond (BusyBox), no hace falta instalar nada más.
#
# Build: docker build -f docker/postgres-backup/Dockerfile -t watchgate-postgres-backup docker/postgres-backup
FROM postgres:16-alpine

# rclone: subida opcional del backup a S3 (o cualquier proveedor
# compatible -- MinIO, Backblaze B2, Wasabi, Cloudflare R2...) vía
# WATCHGATE_BACKUP_S3_BUCKET, ver backup.sh. Un solo binario estático de
# apk, sin dependencias de Python/Go extra que arrastrar a esta imagen ya
# de por sí mínima.
RUN apk add --no-cache rclone

COPY backup.sh /usr/local/bin/backup.sh
RUN chmod +x /usr/local/bin/backup.sh

# Hora configurable vía WATCHGATE_BACKUP_CRON (formato crontab estándar,
# UTC) -- por defecto, todos los días a las 03:00 UTC. `env >
# /etc/environment` antes de escribir el crontab: crond por defecto NO
# hereda las variables de entorno del contenedor (PGPASSWORD,
# WATCHGATE_BACKUP_DIR...) en los jobs que lanza, así que sin esto
# backup.sh se ejecutaría sin credenciales.
COPY docker-entrypoint-backup.sh /usr/local/bin/docker-entrypoint-backup.sh
RUN chmod +x /usr/local/bin/docker-entrypoint-backup.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint-backup.sh"]
