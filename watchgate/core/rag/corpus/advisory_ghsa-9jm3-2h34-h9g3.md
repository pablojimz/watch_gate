# Aviso: Malicious code in gcphelpit (PyPI) (GHSA-9jm3-2h34-h9g3)

## Resumen

During initialization of the CLI, the package exfiltrates sensitive files. Prior version 0.1.2 the code was launching a calculator as PoC instead of exfiltrating data.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-09-gcphelpit

Reasons (based on the campaign):

 - files-exfiltration

## Paquetes afectados

- `gcphelpit` (pip), versiones afectadas: = 0.1.0
- `gcphelpit` (pip), versiones afectadas: = 0.1.1
- `gcphelpit` (pip), versiones afectadas: = 0.1.2

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-01T18:30:29Z
- Fuente: https://github.com/advisories/GHSA-9jm3-2h34-h9g3

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `gcphelpit`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
