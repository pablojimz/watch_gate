# Aviso: Malicious code in modules-newline (npm) (GHSA-5prp-v9g3-92pq)

## Resumen

package.json declares the package's own name, modules-newline, as both a dependency and devDependency pointing to http://pack.nppacks.com/npm/modules-newline instead of the npm registry. On npm install, npm fetches and installs whatever tarball is currently served from that URL, bypassing registry auditing. The URL is plain HTTP (subject to MITM substitution), unpinned (no tag, commit, or integrity hash), and hosted on a non-publisher domain unrelated to npm. Any project that installs this package, directly or transitively, executes code delivered from that external endpoint at install time, including any lifecycle scripts inside the fetched tarball. The shipped index.js is a near-verbatim copy of babel-plugin-transform-define preceded by a comment stating 'This package use for Security Research Testing Purpose.', and the package name does not correspond to the copied plugin's function.

## Paquetes afectados

- `modules-newline` (npm), versiones afectadas: = 0.0.6

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-5prp-v9g3-92pq

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `modules-newline`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
