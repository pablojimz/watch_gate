# Aviso: Malicious code in dlmm-sdk (PyPI) (GHSA-jp82-pmg9-xvj9)

## Resumen

## Source: kam193 (007be0fc2d53a2c72f277ddb12c24bb04ae1e17d2bf03f83b70367c3bf1b9122)
During import the package exfiltrates sensitive env variables and credential files. In addition, listings of cryptocurrency wallet directories are collected.


---

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.


Campaign: 2026-08-dlmm


Reasons (based on the campaign):


 - exfiltration-env-variables


 - dependency-confusion


 - exfiltration-credentials


 - crypto-related

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/12a61d4a44f29287bbd6ed262153cc170ea4d2b3/osv/malicious/pypi/dlmm-sdk/MAL-2026-13729.json))

## Paquetes afectados

- `dlmm-sdk` (pip), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-11T09:32:36Z
- Fuente: https://github.com/advisories/GHSA-jp82-pmg9-xvj9

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
