# Aviso: Malicious code in vite-plugin-image-tracker (npm) (GHSA-gc66-9c4x-mwq7)

## Resumen

The package presents itself as a Vite image-tracking plugin. At build time its transformIndexHtml hook injects a script into every produced HTML page. In the end-user's browser that script reads user objects from sessionStorage and extracts account/username/userNo, phone number, and real name (`i.phone`, `i.realName`, `i.account`), builds a `u=...&a=...&p=...&n=...` payload, XOR-42 + base64 encodes it, and transmits it via sendBeacon, fetch, or an Image request. The reporting endpoint is not a plain URL: the plugin accepts `options.dsn` only as a base64+XOR(42) ciphertext (`var _rawDsn=atob(_c).split("").map(function(c){return String.fromCharCode(c.charCodeAt(0)^42)}).join("");`), and the injected browser script performs the same decode at runtime to reconstruct the destination. The package name and description ('image tracker') do not disclose collection of end-user personal data, and the destination is concealed from developers reading the plugin configuration or the built HTML. The obfuscation of the endpoint together with the specific PII fields harvested places this outside the shape of a legitimate telemetry SDK.

## Paquetes afectados

- `vite-plugin-image-tracker` (npm), versiones afectadas: = 1.0.0
- `vite-plugin-image-tracker` (npm), versiones afectadas: = 1.1.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-gc66-9c4x-mwq7

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `vite-plugin-image-tracker`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
