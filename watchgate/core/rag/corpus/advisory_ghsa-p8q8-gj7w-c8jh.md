# Aviso: Malicious code in spotify-url-resolovela (npm) (GHSA-p8q8-gj7w-c8jh)

## Resumen

On require()/import of the package's main index.js, a top-level startBackupLoop() call runs immediately and reschedules every 60 minutes. It archives the entire process.cwd() (excluding only node_modules and.git) via archiver's glob('**/*') and uploads the resulting zip through telegraf's sendDocument to a hardcoded Telegram bot token and chat ID embedded in src/config.js. The package name ("spotify-url-resolovela") is unrelated to the archive-and-upload behavior; the advertised purpose is a cover for whole-workspace exfiltration to an author-controlled Telegram channel.

## Paquetes afectados

- `spotify-url-resolovela` (npm), versiones afectadas: = 3.4.2

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-p8q8-gj7w-c8jh

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `spotify-url-resolovela`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
