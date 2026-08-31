# Aviso: Malicious code in mt-ts-serverless-starter (npm) (GHSA-23v8-vcgc-99v9)

## Resumen

package.json declares a preinstall hook that runs `node index.js` on every `npm install`. index.js collects installer host identity and system files — os.hostname(), os.userInfo(), home directory, DNS server configuration, /etc/passwd, /etc/hosts, and the full package.json — and HTTPS POSTs the payload to the hardcoded Burp Collaborator subdomain e4jw9ucdu7sdebgoqqx919p6qxwoke83.oastify.com. The exfiltration fires unconditionally at install time with no user interaction.

## Paquetes afectados

- `mt-ts-serverless-starter` (npm), versiones afectadas: = 1.0.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-26T15:31:42Z
- Fuente: https://github.com/advisories/GHSA-23v8-vcgc-99v9

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `mt-ts-serverless-starter`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
