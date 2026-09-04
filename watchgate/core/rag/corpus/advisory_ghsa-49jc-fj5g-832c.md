# Aviso: Malicious code in env-validator-tool (PyPI) (GHSA-49jc-fj5g-832c)

## Resumen

In this campaign, one package contains malicious code exfiltrating environment variables during import (telemetry-helper), and another one intentionally installs it as a dependency.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-09-telemetry-helper

Reasons (based on the campaign):

 - exfiltration-env-variables

 - The malicious code is intentionally included in a dependency of the package

## Paquetes afectados

- `env-validator-tool` (pip), versiones afectadas: = 1.0.0
- `env-validator-tool` (pip), versiones afectadas: = 1.0.1
- `env-validator-tool` (pip), versiones afectadas: = 1.0.2

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-03T03:31:17Z
- Fuente: https://github.com/advisories/GHSA-49jc-fj5g-832c

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `env-validator-tool`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
