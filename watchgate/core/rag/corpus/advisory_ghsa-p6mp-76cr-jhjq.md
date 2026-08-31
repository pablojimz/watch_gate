# Aviso: Malicious code in pyservercheck (PyPI) (GHSA-p6mp-76cr-jhjq)

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

- `pyservercheck` (pip), versiones afectadas: = 0.1.0
- `pyservercheck` (pip), versiones afectadas: = 0.1.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-31T06:30:31Z
- Fuente: https://github.com/advisories/GHSA-p6mp-76cr-jhjq

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `pyservercheck`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
