# Aviso: Malicious code in model-poc-suhail (npm) (GHSA-c6hc-6w4g-fphm)

## Resumen

The package model-poc-suhail was found to contain malicious code.

The OpenSSF Package Analysis project identified 'model-poc-suhail' @ 1.0.14 (npm) as malicious.

It is considered malicious because:

- The package communicates with a domain associated with malicious activity.

## Paquetes afectados

- `model-poc-suhail` (npm), versiones afectadas: = 1.0.5
- `model-poc-suhail` (npm), versiones afectadas: = 1.0.4
- `model-poc-suhail` (npm), versiones afectadas: = 1.0.9
- `model-poc-suhail` (npm), versiones afectadas: = 1.0.14

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-26T09:31:32Z
- Fuente: https://github.com/advisories/GHSA-c6hc-6w4g-fphm

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `model-poc-suhail`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
