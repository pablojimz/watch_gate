# Manual de Despliegue en Producción (TLS & Reverse Proxy)

**WatchGate Production Deployment Guide**
**Ubicación**: `docs/manual_despliegue_prod.md`
**Fecha**: Agosto 2026

---

## 1. Arquitectura de Despliegue en Producción

Para desplegar **WatchGate Enterprise SaaS** en un entorno de producción seguro, se recomienda utilizar una arquitectura en 3 componentes aislados protegidos por un Reverse Proxy con cifrado TLS (HTTPS):

```
                                  [ INTERNET / VIRTUAL PRIVATE CLOUD ]
                                                   |
                                            HTTPS (Puerto 443)
                                                   |
                                                   v
                                 +-----------------------------------+
                                 |   Reverse Proxy (Nginx / Caddy)   |
                                 |   Certificados TLS (Let's Encrypt)|
                                 +-----------------+-----------------+
                                                   |
                             +---------------------+---------------------+
                             |                                           |
                        HTTP (8000)                                 HTTP (8001)
                             v                                           v
             +-------------------------------+           +-------------------------------+
             |     Engine API Server SaaS    |           |       Dashboard Server        |
             |       (FastAPI + Uvicorn)     |           |   (FastAPI + Frontend React)  |
             +---------------+---------------+           +---------------+---------------+
                             |                                           |
                             +---------------------+---------------------+
                                                   |
                                                   v
                                 +-----------------------------------+
                                 |    PostgreSQL Database Cluster    |
                                 |         (Puerto 5432)             |
                                 +-----------------------------------+
```

---

## 2. Configuración del Reverse Proxy (Nginx)

Ejemplo de archivo de configuración `/etc/nginx/sites-available/watchgate.conf`:

```nginx
server {
    listen 80;
    server_name watchgate.internal;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name watchgate.internal;

    ssl_certificate /etc/letsencrypt/live/watchgate.internal/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/watchgate.internal/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 10M;

    # Engine API SaaS (/api/v1/)
    location /api/v1/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Dashboard UI & Backend
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 3. Configuración Alternativa con Caddy (TLS Automático)

Ejemplo de `Caddyfile`:

```caddyfile
watchgate.internal {
    encode gzip

    @api path /api/v1/*
    handle @api {
        reverse_proxy 127.0.0.1:8000
    }

    handle {
        reverse_proxy 127.0.0.1:8001
    }
}
```

---

## 4. Despliegue mediante Docker Compose en Producción

Para arrancar el stack en producción con PostgreSQL:

```bash
# Variables de entorno en .env.production
WATCHGATE_DASHBOARD_DATABASE_URL="postgresql://watchgate:secret_prod_pass@postgres:5432/watchgate_prod"
DEV_MODE="0"
WATCHGATE_DASHBOARD_SECRET_KEY="cifra_secreta_de_32_caracteres_o_mas_para_cookies"
WATCHGATE_DASHBOARD_INGEST_TOKEN="token_de_ingesta_para_github_actions"

# Desplegar stack
docker compose -f docker-compose.yml up -d --build
```
