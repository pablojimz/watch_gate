# Aviso: Malicious code in minecraftmodes (PyPI) (GHSA-m6v9-5p34-2x37)

## Resumen

The package exfiltrates Roblox cookies from the victim machine.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-06-spaysrbdata

Reasons (based on the campaign):

 - infostealer

## Paquetes afectados

- `minecraftmodes` (pip), versiones afectadas: = 0.3.3

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-06T12:30:24Z
- Fuente: https://github.com/advisories/GHSA-m6v9-5p34-2x37

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `minecraftmodes`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
