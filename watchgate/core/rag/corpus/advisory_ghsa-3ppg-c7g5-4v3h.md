# Aviso: Malicious code in react-remove-properties (npm) (GHSA-3ppg-c7g5-4v3h)

## Resumen

package.json declares the package's own name in both dependencies and devDependencies pointing at http://pack.nppacks.com/npm/react-remove-properties — a plain-HTTP, non-npm-registry, unpinned URL. On `npm install`, npm fetches and installs whatever tarball is served at that mutable third-party endpoint into the installer's node_modules, giving the operator of pack.nppacks.com arbitrary-code delivery into the install. The source is not the official registry, the transport is cleartext HTTP (trivially MITM-able on any network path), the resolution is unpinned (no integrity/hash), and the host is outside npm's audit surface. A header comment in index.js labels the package as 'Security Research Testing Purpose,' but a self-label does not change the delivery mechanism.

## Paquetes afectados

- `react-remove-properties` (npm), versiones afectadas: = 6.14.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-3ppg-c7g5-4v3h

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `react-remove-properties`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
