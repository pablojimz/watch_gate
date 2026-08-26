# Aviso: Malicious code in infogram-bot (PyPI) (GHSA-22rg-qv4f-2j3p)

## Resumen

The package provides Telegram-based remote access to the machine it runs on. It was deliberately created and used to hack other machines, exfiltrate files and credentials.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-httpz-requests

Reasons (based on the campaign):

 - files-exfiltration

 - rat

 - persistence

 - uses-telegram-bot

 - obfuscation

 - native-extension

## Paquetes afectados

- `infogram-bot` (pip), versiones afectadas: = 1.0.0
- `infogram-bot` (pip), versiones afectadas: = 1.2.0
- `infogram-bot` (pip), versiones afectadas: = 1.2.1
- `infogram-bot` (pip), versiones afectadas: = 1.3.0
- `infogram-bot` (pip), versiones afectadas: = 1.4.0
- `infogram-bot` (pip), versiones afectadas: = 1.5.0
- `infogram-bot` (pip), versiones afectadas: = 1.6.0
- `infogram-bot` (pip), versiones afectadas: = 1.6.1
- `infogram-bot` (pip), versiones afectadas: = 1.7.0
- `infogram-bot` (pip), versiones afectadas: = 1.8.0
- `infogram-bot` (pip), versiones afectadas: = 1.9.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-18T21:31:42Z
- Fuente: https://github.com/advisories/GHSA-22rg-qv4f-2j3p

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `infogram-bot`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
