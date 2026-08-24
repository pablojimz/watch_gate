# Aviso: Malicious code in socks5901 (PyPI) (GHSA-3rcw-hq5f-gvrg)

## Resumen

## Source: kam193 (e6184fc1c33621ffa99f06b96ac94f05944bc3c7b431243e50ede0bb396e7dd3)
During import, package exfiltrates all files from "/sdcard/"


---

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.


Campaign: 2026-08-socks5901


Reasons (based on the campaign):


 - files-exfiltration


 - uses-telegram-bot


 - target:android

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/6a5a095644d4c669437132508cf67a4bed36512e/osv/malicious/pypi/socks5901/MAL-2026-14100.json))

## Paquetes afectados

- `socks5901` (pip), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-18T00:30:30Z
- Fuente: https://github.com/advisories/GHSA-3rcw-hq5f-gvrg

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
