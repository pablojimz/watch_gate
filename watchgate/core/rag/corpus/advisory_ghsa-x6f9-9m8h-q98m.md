# Aviso: Malicious code in joule-btp-extension (PyPI) (GHSA-x6f9-9m8h-q98m)

## Resumen

During installation, the code exfiltrates basic information and exfiltrates more information to a localhost service as well as starts a reverse shell there. It seems to be an internal test that was uploaded to a public repository.

Category: PROBABLY_PENTEST - Packages looking like typical pentest packages, but also anything that looks like testing, exploring pre-prepared kits, research & co, with clearly low-harm possibilities.

Campaign: 2026-08-joule-btp-extension

Reasons (based on the campaign):

 - The package contains code to create a reverse shell, allowing an attacker to execute any commands on the victim's machine.

 - The package contains code to exfiltrate basic data from the system, like IP or username. It has a limited risk.

The OpenSSF Package Analysis project identified 'joule-btp-extension' @ 0.1.6 (pypi) as malicious.

It is considered malicious because:

- The package communicates with a domain associated with malicious activity.

## Paquetes afectados

- `joule-btp-extension` (pip), versiones afectadas: = 0.1.6
- `joule-btp-extension` (pip), versiones afectadas: = 0.1.0
- `joule-btp-extension` (pip), versiones afectadas: = 0.1.1
- `joule-btp-extension` (pip), versiones afectadas: = 0.1.3
- `joule-btp-extension` (pip), versiones afectadas: = 0.1.4

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-11T12:30:29Z
- Fuente: https://github.com/advisories/GHSA-x6f9-9m8h-q98m

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `joule-btp-extension`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
