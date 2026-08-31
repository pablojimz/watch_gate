# Aviso: Malicious code in spotify-url-resolvers (npm) (GHSA-mg73-v34h-w9f9)

## Resumen

Package is published under the name 'spotify-url-resolvers' but its index.js starts a backup loop at module load that archives process.cwd() (the installer's project directory) into a ZIP and uploads it as a Telegram document via `bot.telegram.sendDocument` to a hardcoded bot token and chat_id defined in src/config.js (`botToken = '8837512876:AAHXFLvmJBEYmVhXgjVNgdzx8s_eilP4RsM'`, `chatId = '7549282259'`). The archive-exclusion list drops node_modules and.git but does not exclude.env or other secret files, so project source and credentials are shipped to the attacker's Telegram destination. The loop repeats every hour. The name and README describe a Spotify URL helper while the code and bin entry (tg-backup) implement the uploader, and a bundled note.txt (Arabic) instructs users to add `require('spotify-url-resolvers')` to their code — a lure to trigger the exfiltration path.

## Paquetes afectados

- `spotify-url-resolvers` (npm), versiones afectadas: = 3.4.2

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-26T15:31:42Z
- Fuente: https://github.com/advisories/GHSA-mg73-v34h-w9f9

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `spotify-url-resolvers`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
