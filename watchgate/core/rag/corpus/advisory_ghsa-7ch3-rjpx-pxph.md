# Aviso: Malicious code in hydration-cls-ui (npm) (GHSA-7ch3-rjpx-pxph)

## Resumen

The package advertises itself as a dependency-free streak/date-math library but ships an x86_64 Linux ELF at dist/internal/calc.dat and auto-launches it. The main module dist/index.mjs contains a top-level IIFE that resolves the binary path, verifies a hardcoded SHA-256, chmods it to 0755, and spawns it detached via cp.spawn with stdio 'pipe' and shell false — running the moment any consumer imports the package. The internal daymath.mjs _ensureEngine() is a stub returning true, so the ELF has no computational role. Strings inside calc.dat identify a full remote-access tool ("RedShell") with a /redshell command dispatcher exposing socks, portfwd, bin, elf, and persist subcommands, a SOCKS5 proxy, TCP port forwarding, arbitrary /bin/sh command execution with output capture, and TLS beaconing (libssl.so.3) to a hardcoded C2 at 217.60.77.63. Second-stage delivery uses curl to fetch ELF payloads from http://217.60.77.63/Others/<file> and shellcode from http://217.60.77.63/SC/<file>, executed via memfd_create (syscall 319) or /tmp/.elf_XXXXXX staging with chmod +x, plus a dropper reference to https://litterbox.catbox.moe/resources/internals/api.php. Bulk exfiltration is implemented as chunked POST /api/extract-receive HTTP/1.1 with Content-Type: application/octet-stream to the C2, alongside /ssh_keys, /creds, /dbfind, /download, /upload, /env, and /clipboard handlers that harvest SSH keys, credential stores, environment variables, and clipboard contents. Persistence is installed by writing ~/.config/systemd/user/svc-update.service (Description="System Update Service", ExecStart=/proc/self/exe, Restart=always) and enabling it with systemctl --user daemon-reload && systemctl --user enable --now, with additional cron, ~/.bashrc, and XDG-autostart branches. The README lists the shipped file as internal/calc-cache.bin while the actual name is internal/calc.dat, and wrapper comments describe it as a "native math accelerator" and "integrity verification — critical security gate", disguising the ELF payload.

## Paquetes afectados

- `hydration-cls-ui` (npm), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-7ch3-rjpx-pxph

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `hydration-cls-ui`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
