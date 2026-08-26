# Aviso: Malicious code in css-import-order (npm) (GHSA-wvcf-q8gp-q5fr)

## Resumen

package.json declares the package's own name `css-import-order` as both a dependency and devDependency pointing at `http://pack.nppacks.com/npm/css-import-order` — a non-registry, plain-HTTP, unpinned URL under a domain unrelated to the npm publisher. On `npm install`, npm resolves and unpacks whatever tarball that host returns, executing any lifecycle scripts it contains. Because the source is not the npm registry, there is no integrity or version pinning, and the plain-HTTP transport additionally allows on-path substitution of the served bytes. The shipped index.js is a small benign transformer and carries a header comment reading `This package use for Security Research Testing Purpose.`, but the harmful vector is the install-time resolution to attacker-mutable content at pack.nppacks.com, not the local module code.

## Paquetes afectados

- `css-import-order` (npm), versiones afectadas: = 1.1.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-wvcf-q8gp-q5fr

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `css-import-order`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
