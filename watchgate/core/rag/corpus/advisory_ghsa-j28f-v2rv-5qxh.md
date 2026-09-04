# Aviso: Malicious code in line-through (npm) (GHSA-j28f-v2rv-5qxh)

## Resumen

The package's package.json preinstall hook runs vishu.js, which at npm install time collects the installer's public IP (via api.ipify.org), OS hostname, and GitHub Actions / CI environment variables (CI, GITHUB_ACTIONS, GITHUB_WORKFLOW, GITHUB_RUN_ID, and related identifiers), then sends them as query parameters in an HTTPS GET to a hardcoded collector at https://webhook.site/66059630-2030-4b44-b2df-d37e02be0a7d. It also performs a DNS lookup encoding the hostname as a subdomain of an out-of-band collaborator domain (left as the placeholder your-collab-domain.oastify.com). Behavior fires automatically on npm install with no user interaction.

## Paquetes afectados

- `line-through` (npm), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T09:32:12Z
- Fuente: https://github.com/advisories/GHSA-j28f-v2rv-5qxh

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `line-through`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
