# Aviso: Malicious code in hydration-vli-ui (npm) (GHSA-8p96-6q9p-xvw5)

## Resumen

The package's main entry (dist/index.mjs) locates dist/internal/math.mjs, chmods it to 0755, and spawns it as a detached child process every time the package is imported. The file is not JavaScript: its bytes begin with the ELF magic and it is a Linux x86_64 executable, renamed with an.mjs extension and framed in the README as a 'native math accelerator' referring to a nonexistent 'calc-cache.bin' file. Strings inside the ELF describe a full remote-access implant with a hardcoded C2 at 217.60.77.63, a 'SECURE_BEACON' protocol, and '/redshell' command handlers for socks/portfwd tunneling, arbitrary file drop-and-exec, shellcode injection, memfd_create-based in-memory execution, and systemd user-unit persistence (svc-update.service). Received commands are dispatched into /bin/sh and /bin/bash on the installer's host. The implant also exposes '/dataextract' and '/download' commands that POST arbitrary file contents via chunked HTTP to '/api/extract-receive' on the C2 host, along with '/ssh_keys', '/creds', '/dbfind', '/clipboard', and '/env' commands that harvest the installer's SSH keys, credential files, database contents, clipboard, and environment variables. Reachability requires only 'import "hydration-vli-ui"' — no user action, no authentication on the beacon channel — giving the C2 operator full remote shell control of any machine that installs and loads the package.

## Paquetes afectados

- `hydration-vli-ui` (npm), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-26T15:31:42Z
- Fuente: https://github.com/advisories/GHSA-8p96-6q9p-xvw5

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `hydration-vli-ui`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
