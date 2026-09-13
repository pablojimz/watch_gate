# Aviso: Malicious code in proxycer (PyPI) (GHSA-qff6-cqrr-65wv)

## Resumen

Packages are designed to collect basic info about the user  when importing them, and have no other purpose. While they claim to do so, some packages from the same uploader use confusing names, clearly suggesting the intention to harvest data from unintentional installations.

Category: PROBABLY_PENTEST - Packages looking like typical pentest packages, but also anything that looks like testing, exploring pre-prepared kits, research & co, with clearly low-harm possibilities.

Campaign: 2025-02-pxz

Reasons (based on the campaign):

 - The package contains code to exfiltrate basic data from the system, like IP or username. It has a limited risk.

 - typosquatting

## Paquetes afectados

- `proxycer` (pip), versiones afectadas: = 0.1.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-05T09:30:22Z
- Fuente: https://github.com/advisories/GHSA-qff6-cqrr-65wv

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `proxycer`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
