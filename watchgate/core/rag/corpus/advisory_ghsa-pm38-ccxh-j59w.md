# Aviso: Malicious code in httpz-requests (PyPI) (GHSA-pm38-ccxh-j59w)

## Resumen

The package provides Telegram-based remote access to the machine it runs on. It was deliberately created and used to hack other machines, exfiltrate files and credentials. This package automatically ensures persistence and starts a malicious process on import.

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

- `httpz-requests` (pip), versiones afectadas: = 1.8.0
- `httpz-requests` (pip), versiones afectadas: = 1.9.0
- `httpz-requests` (pip), versiones afectadas: = 1.10.0
- `httpz-requests` (pip), versiones afectadas: = 1.11.0
- `httpz-requests` (pip), versiones afectadas: = 1.12.0
- `httpz-requests` (pip), versiones afectadas: = 1.13.0
- `httpz-requests` (pip), versiones afectadas: = 1.14.0
- `httpz-requests` (pip), versiones afectadas: = 1.15.0
- `httpz-requests` (pip), versiones afectadas: = 1.16.0
- `httpz-requests` (pip), versiones afectadas: = 1.17.0
- `httpz-requests` (pip), versiones afectadas: = 1.18.0
- `httpz-requests` (pip), versiones afectadas: = 1.19.0
- `httpz-requests` (pip), versiones afectadas: = 1.20.0
- `httpz-requests` (pip), versiones afectadas: = 1.21.0
- `httpz-requests` (pip), versiones afectadas: = 1.21.1
- `httpz-requests` (pip), versiones afectadas: = 1.21.2
- `httpz-requests` (pip), versiones afectadas: = 1.21.3
- `httpz-requests` (pip), versiones afectadas: = 1.21.4
- `httpz-requests` (pip), versiones afectadas: = 1.21.5
- `httpz-requests` (pip), versiones afectadas: = 1.21.6
- `httpz-requests` (pip), versiones afectadas: = 1.21.7
- `httpz-requests` (pip), versiones afectadas: = 1.21.8
- `httpz-requests` (pip), versiones afectadas: = 1.21.9
- `httpz-requests` (pip), versiones afectadas: = 1.21.10
- `httpz-requests` (pip), versiones afectadas: = 1.21.11
- `httpz-requests` (pip), versiones afectadas: = 1.21.12
- `httpz-requests` (pip), versiones afectadas: = 1.21.13
- `httpz-requests` (pip), versiones afectadas: = 1.21.14
- `httpz-requests` (pip), versiones afectadas: = 1.21.15
- `httpz-requests` (pip), versiones afectadas: = 1.21.16
- `httpz-requests` (pip), versiones afectadas: = 1.21.17
- `httpz-requests` (pip), versiones afectadas: = 1.21.18
- `httpz-requests` (pip), versiones afectadas: = 1.21.19
- `httpz-requests` (pip), versiones afectadas: = 1.21.20

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-18T21:31:41Z
- Fuente: https://github.com/advisories/GHSA-pm38-ccxh-j59w

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `httpz-requests`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
