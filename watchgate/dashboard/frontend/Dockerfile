# Imagen del frontend del Dashboard (React + Vite). Build multi-stage:
# compila los estáticos con Node y los sirve con nginx, que además
# reenvía /api/* al backend -- el frontend en dev llama a rutas relativas
# /api/... confiando en el proxy de Vite (ver vite.config.ts); en
# producción, sin ese proxy, nginx tiene que jugar el mismo papel para que
# el código de la app no necesite saber la URL absoluta del backend.
#
# Build:  docker build -t watchgate-dashboard-frontend .
# Run:    docker run -p 8080:80 -e BACKEND_ORIGIN=http://dashboard-backend:8000 watchgate-dashboard-frontend

FROM node:20-slim AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html

# Valor por defecto para `docker run` suelto (fuera de docker-compose.yml,
# donde se sobreescribe con el nombre del servicio del backend) --
# nginx:alpine ya trae `envsubst` sobre /etc/nginx/templates/*.template al
# arrancar (imagen oficial, desde 1.19), no hace falta entrypoint propio.
ENV BACKEND_ORIGIN=http://localhost:8000

EXPOSE 80
