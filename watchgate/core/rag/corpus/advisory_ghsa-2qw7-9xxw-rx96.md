# Aviso: Malicious code in vxhjkseuiaqkb (npm) (GHSA-2qw7-9xxw-rx96)

## Resumen

Published as part of a ClickFix-style fake-CAPTCHA phishing campaign documented by OX Security (see reference). The package's only file is index.html, declared as the npm "main" entry; package.json defines no preinstall/install/postinstall/prepare lifecycle script, so the payload does not execute at `npm install` time. index.html renders a fake Cloudflare Turnstile verification widget. An obfuscator.io-obfuscated inline script builds a hardcoded redirect URL to https://login.microsofte.live/ (a typosquat of a Microsoft sign-in domain), appends the visitor's original query-string parameters, and navigates the browser there via window.location.replace(). The package therefore does not attack the installing machine directly; it is used as a static file host on the npm CDN (e.g. unpkg/jsDelivr) so the index.html can be linked to and opened directly in a victim's browser as a phishing/ClickFix landing page. Published by npm user "johnvaldez9a" as part of a burst of near-identical single-purpose packages published between 2026-08-04 and 2026-08-24 that share this same fake-Turnstile-redirect page structure.

## Paquetes afectados

- `vxhjkseuiaqkb` (npm), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-31T09:30:35Z
- Fuente: https://github.com/advisories/GHSA-2qw7-9xxw-rx96

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `vxhjkseuiaqkb`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
