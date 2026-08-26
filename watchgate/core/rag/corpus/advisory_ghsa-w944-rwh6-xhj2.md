# Aviso: Malicious code in joule-sbx-poc (PyPI) (GHSA-w944-rwh6-xhj2)

## Resumen

During installation, the code exfiltrates basic information and exfiltrates more information to a localhost service as well as starts a reverse shell there. It seems to be an internal test that was uploaded to a public repository.

Category: PROBABLY_PENTEST - Packages looking like typical pentest packages, but also anything that looks like testing, exploring pre-prepared kits, research & co, with clearly low-harm possibilities.

Campaign: 2026-08-joule-btp-extension

Reasons (based on the campaign):

 - The package contains code to create a reverse shell, allowing an attacker to execute any commands on the victim's machine.

 - The package contains code to exfiltrate basic data from the system, like IP or username. It has a limited risk.

## Paquetes afectados

- `joule-sbx-poc` (pip), versiones afectadas: = 0.1.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-11T21:31:31Z
- Fuente: https://github.com/advisories/GHSA-w944-rwh6-xhj2

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `joule-sbx-poc`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
