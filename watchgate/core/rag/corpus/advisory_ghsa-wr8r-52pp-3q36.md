# Aviso: Malicious code in py-0requests (PyPI) (GHSA-wr8r-52pp-3q36)

## Resumen

During import, the code exfiltrates potentially sensitive env variables. In all analyzed versions the exfiltration target was a localhost, suggesting it was just a test.

Category: PROBABLY_PENTEST - Packages looking like typical pentest packages, but also anything that looks like testing, exploring pre-prepared kits, research & co, with clearly low-harm possibilities.

Campaign: 2026-09-0requests

Reasons (based on the campaign):

 - exfiltration-env-variables

 - typosquatting

## Paquetes afectados

- `py-0requests` (pip), versiones afectadas: = 0.0.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-03T18:31:17Z
- Fuente: https://github.com/advisories/GHSA-wr8r-52pp-3q36

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `py-0requests`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
