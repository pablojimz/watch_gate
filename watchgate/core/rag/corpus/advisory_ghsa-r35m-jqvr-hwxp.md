# Aviso: Malicious code in telemetry-helper (PyPI) (GHSA-r35m-jqvr-hwxp)

## Resumen

On `import telemetry_helper`, top-level code starts a daemon thread that sleeps 30 seconds and then POSTs a JSON payload containing the hostname, username, current working directory, and the entire process environment (`dict(os.environ)`) to a hardcoded webhook.site inbox at https://webhook.site/e32d3b8a-a5df-40cc-ae60-7a8343b581e4. `os.environ` on developer and CI hosts routinely contains credential-grade variables (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY, GITHUB_TOKEN, NPM_TOKEN, PYPI_TOKEN / TWINE_PASSWORD, database URLs, private keys), so this is a bulk credential and host-identity harvester. The destination is an anonymous third-party webhook inbox unrelated to any declared publisher, and the 30-second delay before the POST is consistent with evasion of short-lived install/import sandboxes. The behavior fires unconditionally at import with no opt-out and no relation to any advertised functionality.

In this campaign, one package contains malicious code exfiltrating environment variables during import (telemetry-helper), and another one intentionally installs it as a dependency.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-09-telemetry-helper

Reasons (based on the campaign):

 - exfiltration-env-variables

 - The malicious code is intentionally included in a dependency of the package

## Paquetes afectados

- `telemetry-helper` (pip), versiones afectadas: = 1.0.1
- `telemetry-helper` (pip), versiones afectadas: = 2.0.0
- `telemetry-helper` (pip), versiones afectadas: = 1.1.0
- `telemetry-helper` (pip), versiones afectadas: = 1.0.0
- `telemetry-helper` (pip), versiones afectadas: = 1.0.2
- `telemetry-helper` (pip), versiones afectadas: = 1.2.0
- `telemetry-helper` (pip), versiones afectadas: = 1.3.0
- `telemetry-helper` (pip), versiones afectadas: = 2.0.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-03T03:31:17Z
- Fuente: https://github.com/advisories/GHSA-r35m-jqvr-hwxp

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `telemetry-helper`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
