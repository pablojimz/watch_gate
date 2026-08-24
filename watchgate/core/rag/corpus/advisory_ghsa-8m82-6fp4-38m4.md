# Aviso: Malware in conversa-sdk (GHSA-8m82-6fp4-38m4)

## Resumen

Any computer that has this package installed or running should be considered fully compromised. All secrets and keys stored on that computer should be rotated immediately from a different computer. The package should be removed, but as full control of the computer may have been given to an outside entity, there is no guarantee that removing the package will remove all malicious software resulting from installing it.

## Paquetes afectados

- `conversa-sdk` (npm), versiones afectadas: = 1.0.0
- `conversa-sdk` (npm), versiones afectadas: = 1.0.4
- `conversa-sdk` (npm), versiones afectadas: = 1.0.5
- `conversa-sdk` (npm), versiones afectadas: = 1.0.6
- `conversa-sdk` (npm), versiones afectadas: = 1.0.8
- `conversa-sdk` (npm), versiones afectadas: = 1.0.9
- `conversa-sdk` (npm), versiones afectadas: = 2.0.0
- `conversa-sdk` (npm), versiones afectadas: = 2.0.2
- `conversa-sdk` (npm), versiones afectadas: = 2.0.3
- `conversa-sdk` (npm), versiones afectadas: = 2.0.4

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-24T03:12:55Z
- Fuente: https://github.com/advisories/GHSA-8m82-6fp4-38m4

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
