# Aviso: Malicious code in decoris (PyPI) (GHSA-v4c9-8j66-3xg2)

## Resumen

The package exfiltrates Roblox cookies from the victim machine.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-06-spaysrbdata

Reasons (based on the campaign):

 - infostealer

## Paquetes afectados

- `decoris` (pip), versiones afectadas: = 0.3.0
- `decoris` (pip), versiones afectadas: = 0.3.3

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-27T15:30:29Z
- Fuente: https://github.com/advisories/GHSA-v4c9-8j66-3xg2

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `decoris`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
