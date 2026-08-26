# Aviso: Malicious code in cat-embed-i18n-res (npm) (GHSA-rhrq-fjfx-w79w)

## Resumen

The package's only shipped content, strings.json, is presented as an i18n/translation resource bundle but its values are HTML/JavaScript XSS payloads rather than localized text. Multiple entries use `<img src=x onerror=...>` and `<svg onload=...>` handlers that invoke fetch() against the hardcoded endpoint https://notpismo.cloud/c, sending `document.domain` and `document.cookie` as query parameters. Any consumer application that renders these strings as HTML (the ordinary use of an i18n bundle in web UIs) will execute the injected script in the end-user's browser and transmit that user's session cookies and hosting domain to notpismo.cloud. The package name and framing as a translation resource are a cover for the payload; there is no legitimate localization content in the file.

## Paquetes afectados

- `cat-embed-i18n-res` (npm), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-rhrq-fjfx-w79w

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `cat-embed-i18n-res`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
