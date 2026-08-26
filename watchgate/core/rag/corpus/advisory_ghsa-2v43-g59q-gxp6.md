# Aviso: Malicious code in cryptgraphy (PyPI) (GHSA-2v43-g59q-gxp6)

## Resumen

During installation package downloads and executes an executable. The remote executable appears to be broken but suggests intentions for persistence via systemd services, cryptocurrency mining and propagating over the network.  Campaign shows some similarities with 2026-08-boto4

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-mlflow-otel-instrumentor

Reasons (based on the campaign):

 - typosquatting

 - Downloads and executes a remote executable.

 - worm

 - persistence

 - network-scan

 - cryptominer

## Paquetes afectados

- `cryptgraphy` (pip), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-23T21:31:02Z
- Fuente: https://github.com/advisories/GHSA-2v43-g59q-gxp6

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `cryptgraphy`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
