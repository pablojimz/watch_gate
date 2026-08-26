# Aviso: Malicious code in rce-test (PyPI) (GHSA-5j7w-88pp-6hpr)

## Resumen

Installing the package or importing the module exfiltrates basic information about the host, and the package has no other purpose.

Category: PROBABLY_PENTEST - Packages looking like typical pentest packages, but also anything that looks like testing, exploring pre-prepared kits, research & co, with clearly low-harm possibilities.

Campaign: GENERIC-standard-pypi-install-pentest

Reasons (based on the campaign):

 - The package contains code to exfiltrate basic data from the system, like IP or username. It has a limited risk.

 - The package overrides the install command in setup.py to execute malicious code during installation.

## Paquetes afectados

- `rce-test` (pip), versiones afectadas: = 0.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-26T06:31:11Z
- Fuente: https://github.com/advisories/GHSA-5j7w-88pp-6hpr

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `rce-test`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
