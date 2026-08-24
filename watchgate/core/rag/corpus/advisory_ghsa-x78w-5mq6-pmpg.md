# Aviso: Malicious code in telebot-pro (PyPI) (GHSA-x78w-5mq6-pmpg)

## Resumen

## Source: kam193 (610b15fa9ed3d59133ac59b1104d43337faddd2ee77eaf21fd238bea6ac4f540)
When using the provided bot class, the code starts a hidden exfiltration thread that collects Telegram session files, pictures and information about the machine, like connected WiFi networks.


---

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.


Campaign: 2026-08-telebot-pro


Reasons (based on the campaign):


 - uses-telegram-bot


 - action-hidden-in-lib-usage


 - files-exfiltration


 - target:telegram

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/f94d3c298d2a9658982a99894c2f440906257d14/osv/malicious/pypi/telebot-pro/MAL-2026-13757.json))

## Paquetes afectados

- `telebot-pro` (pip), versiones afectadas: = 2.3.7
- `telebot-pro` (pip), versiones afectadas: = 2.3.8

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-11T21:31:31Z
- Fuente: https://github.com/advisories/GHSA-x78w-5mq6-pmpg

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
