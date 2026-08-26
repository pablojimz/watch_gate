# Aviso: Malicious code in mham-js (npm) (GHSA-9g9c-6h9f-qh35)

## Resumen

On import of mham-js, src/api/session-api.js runs top-level code that reads a file outside the package tree at../../../../public/logo.ico, decrypts its contents with CryptoJS.DES using the hardcoded password 'bf497c0b9cee', then spawns a detached node subprocess and pipes the decrypted bytes to its stdin for execution. The loader is disguised with cover-story names ('readLogoIco', 'rsa_exec', 'ThetaSDK initialization error'), and the README states the package does nothing on import, contradicting the actual behavior. The executed payload is stored encrypted outside the tarball, is not verified or documented, and consists of opaque attacker-controlled bytes handed directly to the Node interpreter as arbitrary code.

## Paquetes afectados

- `mham-js` (npm), versiones afectadas: = 1.0.4

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-9g9c-6h9f-qh35

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `mham-js`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
