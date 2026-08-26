# Aviso: Malicious code in digitalexp-style-module-l9 (npm) (GHSA-9xhc-fq73-45jp)

## Resumen

package.json declares both preinstall and postinstall as `node beacon.js`, so beacon.js runs automatically on every `npm install`. beacon.js reads os.hostname(), os.userInfo().username, process.cwd(), and the package name, hex-encodes the collected string, splits it into <=60-char DNS labels, and issues a DNS lookup against those labels under the author-controlled domain b0.rs. It additionally issues an HTTPS GET to https://b0.rs/?poc=...&host=...&cwd=... carrying the same fields in the query string. A source comment identifies the DNS-tunnel channel as chosen for its 'best chance of escaping egress-filtered CI', confirming the dual-channel design is intentional evasion. The version number 99.0.0 is consistent with a dependency-confusion payload targeting internal-scope name resolution.

## Paquetes afectados

- `digitalexp-style-module-l9` (npm), versiones afectadas: = 99.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T06:31:24Z
- Fuente: https://github.com/advisories/GHSA-9xhc-fq73-45jp

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `digitalexp-style-module-l9`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
