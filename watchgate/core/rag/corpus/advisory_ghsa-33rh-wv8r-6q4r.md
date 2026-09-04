# Aviso: Malicious code in box-sign-client-poc (npm) (GHSA-33rh-wv8r-6q4r)

## Resumen

package.json declares a preinstall hook that runs index.js on `npm install`. The script reads the installer's hostname and OS username, embeds them together with a timestamp into a DNS subdomain of the form `poc-<hostname>-<user>-<timestamp>.iv6mfybhp42k33ysmzi73de5w.canarytokens.com`, and issues a DNS resolution for that name, causing the installer's host and user identifiers to be transmitted to a third-party canarytokens.com collector at install time. The package name and framing indicate a dependency-confusion proof-of-concept targeting a Box-branded internal package, but the exfiltration primitive runs against any machine that installs it.

## Paquetes afectados

- `box-sign-client-poc` (npm), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T09:32:12Z
- Fuente: https://github.com/advisories/GHSA-33rh-wv8r-6q4r

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `box-sign-client-poc`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
