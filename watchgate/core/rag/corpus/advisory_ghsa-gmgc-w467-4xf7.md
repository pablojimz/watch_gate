# Aviso: Malicious code in flask-header-guard (PyPI) (GHSA-gmgc-w467-4xf7)

## Resumen

During installation, the package attempts to exfiltrate sensitive environment variables and files, establish persistence and open a reverse shell. Additionally, the provided Flask middleware embeds a backdoor.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-pygame-renderkit

Reasons (based on the campaign):

 - The package contains code to create a reverse shell, allowing an attacker to execute any commands on the victim's machine.

 - files-exfiltration

 - The package overrides the install command in setup.py to execute malicious code during installation.

 - exfiltration-env-variables

 - persistence

## Paquetes afectados

- `flask-header-guard` (pip), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-29T12:30:27Z
- Fuente: https://github.com/advisories/GHSA-gmgc-w467-4xf7

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `flask-header-guard`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
