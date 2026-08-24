# Aviso: Malicious code in message-compiler (npm) (GHSA-pw4h-7785-7vpj)

## Resumen

## Source: amazon-inspector (f7469b2a666f71db1dd06fd00d6ae630becf97ad6854ff5c8938d2adcb5c8417)
The package declares scripts.preinstall = 'node vishu.js', which runs automatically on npm install. vishu.js resolves the installer's public IP via api.ipify.org, reads CI-related environment variables (CI, GITHUB_ACTIONS, GITHUB_WORKFLOW, GITHUB_RUN_ID and related), and issues an HTTPS GET to a hardcoded webhook.site collector URL carrying those fields. It additionally performs a DNS lookup of a subdomain constructed from os.hostname() under a hardcoded oastify.com (Burp Collaborator) domain, exfiltrating the installer's hostname via DNS. The package name typosquats the scoped @intlify/message-compiler package and its only functional code is this beacon.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/e307a23db650fb76255155feb9c7f2fecd528fef/osv/malicious/npm/message-compiler/MAL-2026-14392.json))

## Paquetes afectados

- `message-compiler` (npm), versiones afectadas: = 9.2.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-24T06:30:34Z
- Fuente: https://github.com/advisories/GHSA-pw4h-7785-7vpj

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
