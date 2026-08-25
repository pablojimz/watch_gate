# Aviso: Malicious code in bigtime (PyPI) (GHSA-28hg-x9rg-9j9w)

## Resumen

## Source: kam193 (79fef30b8024966d3842e702f5f277b66d64b6a4a6af603c9eac0c720a4448d6)
The package contains hidden code to overwrite the built-in "open" function and exfiltrate every write to opened files. Exfiltration watcher is also attached to other files in user's home directory.


---

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.


Campaign: 2026-08-bigtime


Reasons (based on the campaign):


 - files-exfiltration

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/ded261455707ad60e990d18a28e2d0bdcb9d340a/osv/malicious/pypi/bigtime/MAL-2026-13712.json))

## Paquetes afectados

- `bigtime` (pip), versiones afectadas: = 0.1.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-11T00:31:13Z
- Fuente: https://github.com/advisories/GHSA-28hg-x9rg-9j9w

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
