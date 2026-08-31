# Aviso: Malicious code in analytics-v2 (npm) (GHSA-c4w9-3vw5-6h6w)

## Resumen

On npm install, the package's preinstall hook executes index.js which harvests host and user identity data (os.hostname(), os.platform(), os.arch(), os.userInfo() including username/uid/gid/shell, homedir, cwd) and captures the output of the shell commands `whoami` and `id` via child_process. The collected data is serialized as JSON and POSTed to the hardcoded endpoint https://839wbtybgrvpgbqzd0l8po2ozf56tyhn.oastify.com/system-info, a Burp Collaborator (oastify.com) out-of-band interaction subdomain unrelated to any legitimate analytics functionality. The behavior fires automatically as part of the npm install lifecycle with no user interaction.

## Paquetes afectados

- `analytics-v2` (npm), versiones afectadas: = 4.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-26T15:31:41Z
- Fuente: https://github.com/advisories/GHSA-c4w9-3vw5-6h6w

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `analytics-v2`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
