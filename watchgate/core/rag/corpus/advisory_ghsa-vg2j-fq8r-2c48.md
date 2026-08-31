# Aviso: Malicious code in trongridor (PyPI) (GHSA-vg2j-fq8r-2c48)

## Resumen

Package appears to be designed for private key exfiltration, but no known usage. The name appears to be related to the cryptocurrency TRX (Tron / Tronix). Some packages additionally clone the readme of other, legit libraries. The similar packages are repeating uploaded to PyPI

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2025-04-tronix

Reasons (based on the campaign):

 - exfiltration-generic

 - crypto-related

## Paquetes afectados

- `trongridor` (pip), versiones afectadas: = 0.0.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-30T09:30:25Z
- Fuente: https://github.com/advisories/GHSA-vg2j-fq8r-2c48

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `trongridor`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
