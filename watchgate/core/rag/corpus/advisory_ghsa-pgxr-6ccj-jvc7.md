# Aviso: Malicious code in ecobee-home (npm) (GHSA-pgxr-6ccj-jvc7)

## Resumen

The package's declared postinstall script runs beacon.js, which issues an HTTP GET to a hardcoded bare-IP endpoint (http://169.58.96.170:9001/cb) carrying the installer's hostname and the package name as query parameters. This fires automatically on npm install with no user opt-in. Reaching out to a bare-IP over plain HTTP with the installer's hostname on install is host-identifier reconnaissance/exfiltration to an attacker-controlled endpoint; the placeholder README and lookalike package name are consistent with a dependency-confusion / recon beacon rather than legitimate telemetry.

## Paquetes afectados

- `ecobee-home` (npm), versiones afectadas: = 0.0.2

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-pgxr-6ccj-jvc7

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `ecobee-home`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
