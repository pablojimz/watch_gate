# Aviso: Malicious code in chartkit-core (PyPI) (GHSA-qhj3-jww9-gmfc)

## Resumen

Installing the package or importing the module exfiltrates basic information about the host, and the package has no other purpose.

Category: PROBABLY_PENTEST - Packages looking like typical pentest packages, but also anything that looks like testing, exploring pre-prepared kits, research & co, with clearly low-harm possibilities.

Campaign: GENERIC-standard-pypi-install-pentest

Reasons (based on the campaign):

 - The package contains code to exfiltrate basic data from the system, like IP or username. It has a limited risk.

 - The package overrides the install command in setup.py to execute malicious code during installation.

## Paquetes afectados

- `chartkit-core` (pip), versiones afectadas: = 1.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T21:31:33Z
- Fuente: https://github.com/advisories/GHSA-qhj3-jww9-gmfc

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `chartkit-core`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
