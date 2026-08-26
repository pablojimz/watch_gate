# Aviso: Malicious code in socks5901 (PyPI) (GHSA-3rcw-hq5f-gvrg)

## Resumen

During import, package exfiltrates all files from "/sdcard/"

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-socks5901

Reasons (based on the campaign):

 - files-exfiltration

 - uses-telegram-bot

 - target:android

## Paquetes afectados

- `socks5901` (pip), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-18T00:30:30Z
- Fuente: https://github.com/advisories/GHSA-3rcw-hq5f-gvrg

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `socks5901`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
