# Aviso: Malicious code in vite-plugin-image-analysis (npm) (GHSA-9frw-xww8-fcr6)

## Resumen

The package presents itself as a Vite 'image analysis' plugin but contains no image-analysis code. Its `transformIndexHtml` hook injects an inline `<script>` into every built HTML page. The injected script reads user identity fields (`account`/`username`/`userNo`, `phone`, `realName`) from `sessionStorage.userInfo`, hooks `sessionStorage.setItem` so the beacon fires after login writes these fields, and sends the values along with host and OS to a remote endpoint. The destination URL is not a plain literal: a base64 blob is decoded and XOR'd with 42 at runtime in the victim's browser (`atob(_c).split('').map(c => String.fromCharCode(c.charCodeAt(0) ^ 42)).join('')`), and the outbound query string is similarly XOR(42)+base64 wrapped. Delivery uses stealth transports — `navigator.sendBeacon`, `fetch(..., { mode: 'no-cors', referrerPolicy: 'no-referrer' })` — that suppress network-panel visibility and referrer leakage. A developer who adds this plugin to their Vite build unknowingly ships a covert end-user PII scraper into their production site, with the exfil destination hidden from anyone inspecting the built bundle.

## Paquetes afectados

- `vite-plugin-image-analysis` (npm), versiones afectadas: = 1.1.0
- `vite-plugin-image-analysis` (npm), versiones afectadas: = 1.0.0
- `vite-plugin-image-analysis` (npm), versiones afectadas: = 1.1.2

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-9frw-xww8-fcr6

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `vite-plugin-image-analysis`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
