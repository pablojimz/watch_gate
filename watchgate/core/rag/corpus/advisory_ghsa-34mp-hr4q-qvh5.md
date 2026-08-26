# Aviso: Malicious code in kb-ai (PyPI) (GHSA-34mp-hr4q-qvh5)

## Resumen

The main purpose of the package is to demonstrate a dependency confusion attack. The rest of the functionality is just a stub.

Category: PROBABLY_PENTEST - Packages looking like typical pentest packages, but also anything that looks like testing, exploring pre-prepared kits, research & co, with clearly low-harm possibilities.

Campaign: GENERIC-standard-pypi-install-pentest

Reasons (based on the campaign):

 - The package contains code to exfiltrate basic data from the system, like IP or username. It has a limited risk.

 - The package overrides the install command in setup.py to execute malicious code during installation.

## Paquetes afectados

- `kb-ai` (pip), versiones afectadas: = 0.1.0
- `kb-ai` (pip), versiones afectadas: = 0.1.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-16T21:30:26Z
- Fuente: https://github.com/advisories/GHSA-34mp-hr4q-qvh5

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `kb-ai`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
