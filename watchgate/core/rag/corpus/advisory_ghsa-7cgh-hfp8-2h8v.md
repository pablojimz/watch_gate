# Aviso: Malicious code in verify-contract-ethers (npm) (GHSA-7cgh-hfp8-2h8v)

## Resumen

The OpenSSF Package Analysis project identified 'verify-contract-ethers' @ 1.0.0 (npm) as malicious.

It is considered malicious because:

- The package communicates with a domain associated with malicious activity.

- The package executes one or more commands associated with malicious behavior.

## Paquetes afectados

- `verify-contract-ethers` (npm), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-31T00:30:26Z
- Fuente: https://github.com/advisories/GHSA-7cgh-hfp8-2h8v

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `verify-contract-ethers`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
