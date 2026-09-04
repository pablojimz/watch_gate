# Aviso: Malicious code in real-router-telemetry (npm) (GHSA-cwm2-j3h3-g35f)

## Resumen

Package ships telemetry.js, an obfuscated module (string-array accessor pattern hiding identifiers and the destination) that reads host identity (hostname, username, cwd, platform, arch, memory, cpu info), executes `cat /etc/os-release` and `ps aux`, reads `.env` from the current working directory via fs.readFileSync, and POSTs the collected JSON to https://webhook.site/e32d3b8a-a5df-40cc-ae60-7a8343b581e4, an anonymous request-capture endpoint unrelated to any declared publisher. `.env` files in a developer's cwd typically contain API keys, tokens, and other credentials that do not belong to this package. package.json declares a postinstall hook (`node -e "require('./index.js')"`); index.js in this build is a stub (declaring version 1.0.1 while the manifest is 1.0.4) that does not currently require telemetry.js, so the shipped payload is staged but not wired into the install-time entry point in this version. The combination of an obfuscated host-and-secret exfil module targeting an anonymous webhook collector, mismatched version metadata, and an install-time hook aimed at the package's own entry point indicates a malicious package.

## Paquetes afectados

- `real-router-telemetry` (npm), versiones afectadas: = 1.0.1
- `real-router-telemetry` (npm), versiones afectadas: = 1.0.4

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T09:32:12Z
- Fuente: https://github.com/advisories/GHSA-cwm2-j3h3-g35f

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `real-router-telemetry`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
