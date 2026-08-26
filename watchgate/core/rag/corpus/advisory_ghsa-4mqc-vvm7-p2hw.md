# Aviso: Malicious code in cscasereadserv-paypal (npm) (GHSA-4mqc-vvm7-p2hw)

## Resumen

cscasereadserv-paypal@3.4.3 executes a preinstall script that auto-runs on `npm install`. The script collects the installer's OS username, hostname, and current working directory, then walks up parent directories to read the surrounding project's package.json name, author, and version. The collected JSON payload is hex-encoded and exfiltrated in chunks via DNS lookups to attacker-controlled subdomains under `jgl.red` (form: `<seq>.<hex>.x.da5u87oh92rc72pp1dngqfc6hp8gwshm6.o.jgl.red`), with a fallback DNS query on error. A source comment (`// x-hackerone: kokonut`) suggests dependency-confusion / bug-bounty reconnaissance framing, but the payload identifies the installer and discloses the name and version of the surrounding (likely private) parent package to a third party.

## Paquetes afectados

- `cscasereadserv-paypal` (npm), versiones afectadas: = 3.4.3

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-4mqc-vvm7-p2hw

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `cscasereadserv-paypal`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
