# Aviso: Malicious code in boto4 (PyPI) (GHSA-ffh8-mpww-qp8g)

## Resumen

During installation, package executes an embedded executable. The executable is capable of executing remote commands, establishing persistence, cryptomining, exfiltrating basic data, further network scanning and worm-style propagation. Actions are controlled via a Telegram bot.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-boto4

Reasons (based on the campaign):

 - cryptominer

 - worm

 - network-scan

 - The package contains code to exfiltrate basic data from the system, like IP or username. It has a limited risk.

 - uses-telegram-bot

 - persistence

 - The package contains code to execute remote commands (probably limited to a specific set) on the victim's machine.

## Paquetes afectados

- `boto4` (pip), versiones afectadas: = 1.0.0
- `boto4` (pip), versiones afectadas: = 1.0.2

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-21T09:32:06Z
- Fuente: https://github.com/advisories/GHSA-ffh8-mpww-qp8g

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `boto4`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
