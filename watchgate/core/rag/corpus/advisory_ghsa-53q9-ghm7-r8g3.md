# Aviso: Malicious code in pygame-renderkit (PyPI) (GHSA-53q9-ghm7-r8g3)

## Resumen

During installation, the package attempts to exfiltrate sensitive environment variables and files, establish persistence and open reverse shell.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-pygame-renderkit

Reasons (based on the campaign):

 - persistence

 - The package overrides the install command in setup.py to execute malicious code during installation.

 - The package contains code to create a reverse shell, allowing an attacker to execute any commands on the victim's machine.

 - files-exfiltration

 - exfiltration-env-variables

## Paquetes afectados

- `pygame-renderkit` (pip), versiones afectadas: = 1.2.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-28T12:30:30Z
- Fuente: https://github.com/advisories/GHSA-53q9-ghm7-r8g3

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `pygame-renderkit`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
