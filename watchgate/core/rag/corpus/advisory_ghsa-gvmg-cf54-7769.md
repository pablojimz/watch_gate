# Aviso: Malware in vue-template-compiler-plugin (GHSA-gvmg-cf54-7769)

## Resumen

Any computer that has this package installed or running should be considered fully compromised. All secrets and keys stored on that computer should be rotated immediately from a different computer. The package should be removed, but as full control of the computer may have been given to an outside entity, there is no guarantee that removing the package will remove all malicious software resulting from installing it.

## Paquetes afectados

- `vue-template-compiler-plugin` (npm), versiones afectadas: >= 0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T16:53:39Z
- Fuente: https://github.com/advisories/GHSA-gvmg-cf54-7769

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `vue-template-compiler-plugin`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
