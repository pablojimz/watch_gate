# Aviso: Malicious code in discordnv (PyPI) (GHSA-89r4-hq67-cfgq)

## Resumen

On `import discordnv`, __init__.py invokes main_entry() which hides the console window, walks Discord/Chrome/Edge/Brave/Opera/Yandex/Firefox LevelDB/SQLite stores to extract Discord authentication tokens, reads and DPAPI-decrypts Roblox `robloxcookies.dat`, and POSTs the harvested credentials to a hardcoded Discord webhook at discord.com/api/webhooks/1528403989983662194/... and a Google Apps Script endpoint at script.google.com/macros/s/AKfycbwa.../exec. add_to_startup() writes an HKCU\Software\Microsoft\Windows\CurrentVersion\Run entry named `discordnv` pointing at the invoking Python/exe so the stealer re-runs on every user logon. All operations are wrapped in bare try/except to swallow errors and avoid alerting the user. The package's advertised purpose (a Roblox DataStore helper) is unrelated to the observed behavior.

The package exfiltrates Roblox cookies and Discord tokens from the victim machine.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-06-spaysrbdata

Reasons (based on the campaign):

 - infostealer

## Paquetes afectados

- `discordnv` (pip), versiones afectadas: = 0.8.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-27T15:30:29Z
- Fuente: https://github.com/advisories/GHSA-89r4-hq67-cfgq

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `discordnv`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
