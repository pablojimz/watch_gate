# Aviso: Malicious code in commonjs-code-token (npm) (GHSA-wq3w-3cqf-rjjj)

## Resumen

On npm install, the package's postinstall hook runs index.js, which fetches JSON from https://access-token-delta.vercel.app and passes the returned `token` field directly to eval(). Whoever controls that endpoint obtains arbitrary code execution on the installing machine, and the fetched content is mutable at any time. The package advertises itself with a README for an unrelated multithreaded cache library (node-cache-multithread) while the actual package identity is commonjs-code-token, a metadata/behavior mismatch consistent with a cover story. No legitimate functionality is shipped in the package.

## Paquetes afectados

- `commonjs-code-token` (npm), versiones afectadas: = 1.0.1
- `commonjs-code-token` (npm), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-26T15:31:42Z
- Fuente: https://github.com/advisories/GHSA-wq3w-3cqf-rjjj

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `commonjs-code-token`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
