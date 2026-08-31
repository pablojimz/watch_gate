# Aviso: Malicious code in pybitjs (PyPI) (GHSA-wv93-5fvj-96j3)

## Resumen

Package embeds obfuscated, JS-based malware downloading further remote stages. The code is triggered during building the package and on every Python startup (via PTH file). The next-stage IP is delivered via a blockchain. 

The payload and embedded IoCs are consistent with campaigns attributed to Lazarus APT/PolinRider.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-pybitjs

Reasons (based on the campaign):

 - obfuscation

 - Downloads and executes a remote malicious script.

 - malware

 - abuses-pth

 - c2-in-blockchain

## Paquetes afectados

- `pybitjs` (pip), versiones afectadas: = 0.1.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-26T21:31:22Z
- Fuente: https://github.com/advisories/GHSA-wv93-5fvj-96j3

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `pybitjs`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
