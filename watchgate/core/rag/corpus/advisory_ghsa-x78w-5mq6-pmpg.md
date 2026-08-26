# Aviso: Malicious code in telebot-pro (PyPI) (GHSA-x78w-5mq6-pmpg)

## Resumen

When using the provided bot class, the code starts a hidden exfiltration thread that collects Telegram session files, pictures and information about the machine, like connected WiFi networks.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-telebot-pro

Reasons (based on the campaign):

 - uses-telegram-bot

 - action-hidden-in-lib-usage

 - files-exfiltration

 - target:telegram

## Paquetes afectados

- `telebot-pro` (pip), versiones afectadas: = 2.3.7
- `telebot-pro` (pip), versiones afectadas: = 2.3.8

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-11T21:31:31Z
- Fuente: https://github.com/advisories/GHSA-x78w-5mq6-pmpg

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `telebot-pro`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
