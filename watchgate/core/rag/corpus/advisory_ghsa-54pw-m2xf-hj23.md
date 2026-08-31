# Aviso: Malicious code in chai-as-org (npm) (GHSA-54pw-m2xf-hj23)

## Resumen

The package presents itself as a chai/pino-style utility but its index.js unconditionally require()s lib/initializeCaller.js, which on load base64-decodes a hardcoded URL and POSTs the entire process.env of the importing process to https://ipcheck-hashed.vercel.app/api/auth/6c1d60d35852ef0c05df. The response body from that same endpoint is passed to new Function('require', response.data) and immediately invoked with the caller's require, giving the remote server arbitrary code execution inside the Node.js process that imported the package. The destination URL is stored as a base64 literal to evade static inspection, and index.js is a no-op Express-middleware wrapper functioning as a cover story for the load-time exfiltration and RCE in initializeCaller.js.

## Paquetes afectados

- `chai-as-org` (npm), versiones afectadas: = 1.0.5

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-26T15:31:41Z
- Fuente: https://github.com/advisories/GHSA-54pw-m2xf-hj23

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `chai-as-org`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
