# Aviso: Malicious code in @worrisome/reutil (npm) (GHSA-2pgx-9rv6-xj93)

## Resumen

Published as part of a ClickFix-style fake-CAPTCHA phishing campaign documented by OX Security (see reference). The package's only file is index.html, declared as the npm "main" entry; package.json defines no preinstall/install/postinstall/prepare lifecycle script, so the payload does not execute at `npm install` time. index.html renders a fake Cloudflare Turnstile verification widget. An obfuscator.io-obfuscated inline script POSTs a hardcoded per-package "hostKey" to https://api.keyval.org/get, receives a base64-encoded IV:ciphertext pair, decrypts it client-side via the Web Crypto API (AES-CTR) using an embedded key to obtain a redirect URL, appends the visitor's original query-string parameters, and navigates the browser there via window.location.replace(). This "dead drop" design lets the operator change the phishing destination for every package sharing a hostKey without republishing to npm; OX Security observed keyval.org-served destinations including a typosquatted Microsoft login page and, at time of writing, a ChatGPT redirect. The package therefore does not attack the installing machine directly; it is used as a static file host on the npm CDN (e.g. unpkg/jsDelivr) so the index.html can be linked to and opened directly in a victim's browser as a phishing/ClickFix landing page. Published by npm user "cattishly" as part of a burst of near-identical single-purpose packages published between 2026-08-04 and 2026-08-24 that share this same fake-Turnstile-redirect page structure.

## Paquetes afectados

- `@worrisome/reutil` (npm), versiones afectadas: > 0
- `@worrisome/reutil` (npm), versiones afectadas: = 1.0.0
- `@worrisome/reutil` (npm), versiones afectadas: = 1.0.1
- `@worrisome/reutil` (npm), versiones afectadas: = 1.0.2
- `@worrisome/reutil` (npm), versiones afectadas: = 1.0.3

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-31T09:30:34Z
- Fuente: https://github.com/advisories/GHSA-2pgx-9rv6-xj93

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `@worrisome/reutil`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
