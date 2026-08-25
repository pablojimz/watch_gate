# Aviso: Malicious code in infogram-bot (PyPI) (GHSA-22rg-qv4f-2j3p)

## Resumen

## Source: kam193 (454fa32963f58275e35167d59dd581240725e099682e76e44b6fca7b22332cb0)
The package provides Telegram-based remote access to the machine it runs on. It was deliberately created and used to hack other machines, exfiltrate files and credentials.


---

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.


Campaign: 2026-08-httpz-requests


Reasons (based on the campaign):


 - files-exfiltration


 - rat


 - persistence


 - uses-telegram-bot


 - obfuscation


 - native-extension

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/60dfd99c8d9d6c66d1c4b8763867f28895e6264c/osv/malicious/pypi/infogram-bot/MAL-2026-14131.json))

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

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
