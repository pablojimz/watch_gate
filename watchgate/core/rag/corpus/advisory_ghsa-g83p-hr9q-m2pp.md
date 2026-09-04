# Aviso: Malicious code in box-sign-client (npm) (GHSA-g83p-hr9q-m2pp)

## Resumen

box-sign-client@1.0.0 is a dependency-confusion vehicle positioned against the internal Box namespace (@box/sign-client). Its package.json declares a preinstall script (`node index.js`) that reads `os.hostname()` and `process.env.USER`/`USERNAME`, embeds those values into a subdomain of the hardcoded host `iv6mfybhp42k33ysmzi73de5w.canarytokens.com`, and calls `dns.resolve()` to trigger a DNS lookup against that subdomain. On any `npm install` that resolves this public package instead of the intended internal one, the installing host's hostname and login user are transmitted via DNS to a third-party Canarytokens collector at install time, before any application code is run. The package advertises itself as a proof-of-concept for Box dependency confusion, but the beacon fires against any installer regardless of intent.

## Paquetes afectados

- `box-sign-client` (npm), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T09:32:12Z
- Fuente: https://github.com/advisories/GHSA-g83p-hr9q-m2pp

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `box-sign-client`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
