# Aviso: Malicious code in vite-plugin-bug-tracker (npm) (GHSA-hr7f-wpph-3wjg)

## Resumen

The package presents itself as a Vite bug-tracker plugin. Its transformIndexHtml hook injects an inline script into every built HTML page produced by the developer's Vite build. At runtime in the end user's browser, that injected script reads personally identifiable information from sessionStorage (account/username, phone number, real name via fields such as i.phone and i.realName) and transmits it via fetch (mode: 'no-cors'), sendBeacon, or an Image request. The destination URL is not written in cleartext: it is assembled at runtime by base64-decoding a bundled string and XOR-ing each byte with 42 (atob(_c).split('').map(c => String.fromCharCode(c.charCodeAt(0) ^ 42)).join('')). The exfiltration query string is likewise XOR+base64 encoded before being appended. The plugin also monkey-patches sessionStorage.setItem so that any write matching the configured scope triggers immediate exfiltration. As a result, applications built with this plugin ship a PII harvester to their production users whose reporting endpoint cannot be identified by inspecting the built bundle or a browser network trace at a glance.

## Paquetes afectados

- `vite-plugin-bug-tracker` (npm), versiones afectadas: = 1.0.0
- `vite-plugin-bug-tracker` (npm), versiones afectadas: = 1.1.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-hr7f-wpph-3wjg

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `vite-plugin-bug-tracker`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
