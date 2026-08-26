# Aviso: Malicious code in deepface-weights (PyPI) (GHSA-2cw8-w83p-pj7v)

## Resumen

On import, deepface_weights starts a daemon thread that polls every 10 seconds for the file `data/telethon_market_userbot.session` in the current working directory. When found, it POSTs the session file together with the local `os.getlogin()` value to the hardcoded endpoint https://webhook.site/730d2d03-5c78-4e0a-88df-9d8466b7e8aa. A Telethon `.session` file holds authenticated Telegram credentials, so exfiltration enables full takeover of the associated Telegram account. Package metadata is placeholder (author email `rozuvu@example.com`, description `Minimal example Python package`) and the name resembles the unrelated `deepface` face-recognition library, but the package ships none of that functionality — the stealer is its only behavior. Source comments in Russian label the destination as the attacker's server.

During import, package exfiltrates the sensitive file with the Telegram session token.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-deepface-weights

Reasons (based on the campaign):

 - files-exfiltration

 - target:telegram

## Paquetes afectados

- `deepface-weights` (pip), versiones afectadas: = 0.1.0
- `deepface-weights` (pip), versiones afectadas: = 0.1.1
- `deepface-weights` (pip), versiones afectadas: = 0.1.2

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-19T00:31:27Z
- Fuente: https://github.com/advisories/GHSA-2cw8-w83p-pj7v

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `deepface-weights`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
