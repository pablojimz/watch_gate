# Aviso: Malicious code in deepface-weight (PyPI) (GHSA-5j48-33h2-gvwg)

## Resumen

On import, deepface-weight spawns a daemon background thread that polls the installer's working directory for `data/telethon_market_userbot.session` for approximately 10 minutes and POSTs the file to a hardcoded webhook.site endpoint (https://webhook.site/d6ea9c5b-4a85-4e59-9397-2bb5f9407c87). Telethon session files contain live authentication material granting full access to the associated Telegram account. The exfiltration destination is bound to a variable literally named `evil_server_url` with a Russian-language comment identifying it as the attacker's server. The package name mimics the popular `deepface` ML library but ships no machine-learning code; author metadata is a placeholder (`asdqwdasdqwdasd`) with a disposable email at playboot.com.

During import, package exfiltrates the sensitive file with the Telegram session token.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-deepface-weights

Reasons (based on the campaign):

 - files-exfiltration

 - target:telegram

## Paquetes afectados

- `deepface-weight` (pip), versiones afectadas: = 0.1.4

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-19T00:31:27Z
- Fuente: https://github.com/advisories/GHSA-5j48-33h2-gvwg

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `deepface-weight`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
