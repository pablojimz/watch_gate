# Aviso: Malicious code in reqcrypt-dev (PyPI) (GHSA-f4gc-vf6c-945w)

## Resumen

## Source: kam193 (8e66755912c02a4de1ed6f86b092e2a0dcdadbcaef931cbd07c6d2306619f3e4)
The package contains a hidden backdoor. The promised functionality is an HTTP request library with some additional functions. On every usage, code secretly checks for the presence of specific fields in the response, and if they are found, their content is secretly executed.


---

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.


Campaign: 2026-08-reqcrypt


Reasons (based on the campaign):


 - backdoor

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/ffde578b842953a28962fa346230ed4ae580cdd9/osv/malicious/pypi/reqcrypt-dev/MAL-2026-14274.json))

## Paquetes afectados

- `reqcrypt-dev` (pip), versiones afectadas: = 0.1.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-19T09:31:31Z
- Fuente: https://github.com/advisories/GHSA-f4gc-vf6c-945w

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
