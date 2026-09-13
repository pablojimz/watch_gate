# Aviso: Malicious code in trongridew (PyPI) (GHSA-vjjx-756v-6p3x)

## Resumen

Package appears to be designed for private key exfiltration, but no known usage. The name appears to be related to the cryptocurrency TRX (Tron / Tronix). Some packages additionally clone the readme of other, legit libraries. The similar packages are repeating uploaded to PyPI

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2025-04-tronix

Reasons (based on the campaign):

 - exfiltration-generic

 - crypto-related

## Paquetes afectados

- `trongridew` (pip), versiones afectadas: = 0.0.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-05T21:31:20Z
- Fuente: https://github.com/advisories/GHSA-vjjx-756v-6p3x

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `trongridew`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
