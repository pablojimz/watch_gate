# Aviso: Malicious code in dlmm (PyPI) (GHSA-5gh8-34vp-xw63)

## Resumen

## Source: kam193 (044faa804b628c1751f6fa5f66a5f8835ecda1f4d2837ae70411d4630a0607ad)
Installing the package or importing the module exfiltrates basic information about the host, and the package has no other purpose.


---

Category: PROBABLY_PENTEST - Packages looking like typical pentest packages, but also anything that looks like testing, exploring pre-prepared kits, research & co, with clearly low-harm possibilities.


Campaign: GENERIC-standard-pypi-install-pentest


Reasons (based on the campaign):


 - The package contains code to exfiltrate basic data from the system, like IP or username. It has a limited risk.


 - The package overrides the install command in setup.py to execute malicious code during installation.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/ffb643191998a2ee07d2d931c519d99a3fa38bf8/osv/malicious/pypi/dlmm/MAL-2026-13728.json))

## Paquetes afectados

- `dlmm` (pip), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-11T06:31:19Z
- Fuente: https://github.com/advisories/GHSA-5gh8-34vp-xw63

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
