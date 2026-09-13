# Aviso: Malicious code in telegram-helper (PyPI) (GHSA-vxg4-4jxm-7ff9)

## Resumen

The package hides code that starts a Telegram bot to exfiltrate sensitive session files and cookies

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-09-telegram-helper

Reasons (based on the campaign):

 - The package contains code to execute remote commands (probably limited to a specific set) on the victim's machine.

 - rat

 - files-exfiltration

 - target:telegram

 - uses-telegram-bot

 - exfiltration-browser-data

## Paquetes afectados

- `telegram-helper` (pip), versiones afectadas: = 0.1.1
- `telegram-helper` (pip), versiones afectadas: = 0.1.2

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-08T00:30:27Z
- Fuente: https://github.com/advisories/GHSA-vxg4-4jxm-7ff9

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `telegram-helper`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
