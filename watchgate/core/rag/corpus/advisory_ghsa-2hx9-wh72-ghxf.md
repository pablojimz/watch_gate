# Aviso: Malicious code in ecobee2 (npm) (GHSA-2hx9-wh72-ghxf)

## Resumen

package.json declares scripts.postinstall = 'node beacon.js', which runs automatically on npm install. beacon.js performs an HTTP GET to http://169.58.96.170:9001/cb with the installer's os.hostname() and the package name in the query string, disclosing host identity to a hardcoded bare-IP endpoint over cleartext HTTP at install time. The package README is a placeholder and no legitimate purpose is documented for this network activity.

## Paquetes afectados

- `ecobee2` (npm), versiones afectadas: = 0.0.2

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-2hx9-wh72-ghxf

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `ecobee2`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
