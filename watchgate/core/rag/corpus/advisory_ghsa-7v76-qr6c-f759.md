# Aviso: Malicious code in vite-plugin-images-analysis (npm) (GHSA-7v76-qr6c-f759)

## Resumen

This Vite plugin, advertised as an image-analysis tool, uses transformIndexHtml to inject an inline script into every built HTML page produced by the developer's application. The injected script reads end-user identity fields (account/username/userNo, phone, realName) from sessionStorage keys such as 'user' and 'user-store', hooks sessionStorage.setItem to capture values at login time, and transmits them via sendBeacon/fetch/Image requests. The destination URL is not present in cleartext in the source: the plugin's `dsn` option is a base64 string that is XOR-decoded with key 42 in the browser at runtime (atob(_c).split('').map(c=>String.fromCharCode(c.charCodeAt(0)^42)).join('')), and the outbound query string is likewise base64+XOR-encoded before being sent. The declared 'image analysis' purpose does not match the actual behavior of harvesting logged-in-user PII from the consuming application and posting it to a concealed endpoint.

## Paquetes afectados

- `vite-plugin-images-analysis` (npm), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-7v76-qr6c-f759

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `vite-plugin-images-analysis`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
