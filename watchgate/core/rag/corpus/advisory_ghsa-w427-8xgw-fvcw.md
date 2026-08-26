# Aviso: Malicious code in mlflow-otel-instrumentor (PyPI) (GHSA-w427-8xgw-fvcw)

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

- `mlflow-otel-instrumentor` (pip), versiones afectadas: = 1.1.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-23T18:31:49Z
- Fuente: https://github.com/advisories/GHSA-w427-8xgw-fvcw

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `mlflow-otel-instrumentor`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
