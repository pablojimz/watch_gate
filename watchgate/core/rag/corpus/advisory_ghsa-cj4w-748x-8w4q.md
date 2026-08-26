# Aviso: Malicious code in minecraft-ytreceiver (PyPI) (GHSA-cj4w-748x-8w4q)

## Resumen

The package hides code for exfiltrating files, recordings from the webcam, screenshots, keylogging.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-minecraft-ytreceiver

Reasons (based on the campaign):

 - spyware-like

 - files-exfiltration

 - uses-telegram-bot

 - keylogger

## Paquetes afectados

- `minecraft-ytreceiver` (pip), versiones afectadas: = 0.1.0
- `minecraft-ytreceiver` (pip), versiones afectadas: = 0.2.0
- `minecraft-ytreceiver` (pip), versiones afectadas: = 0.3.0
- `minecraft-ytreceiver` (pip), versiones afectadas: = 0.4.0
- `minecraft-ytreceiver` (pip), versiones afectadas: = 0.5.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T21:31:16Z
- Fuente: https://github.com/advisories/GHSA-cj4w-748x-8w4q

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `minecraft-ytreceiver`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
