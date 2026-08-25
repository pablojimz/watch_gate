# Aviso: Malicious code in requests-crypt (PyPI) (GHSA-cf52-hr54-m53p)

## Resumen

## Source: kam193 (eee14db4ceeeedc62311a8926bc641b77f2cce3345e5f9b6083663f8931cb92b)
The package contains a hidden backdoor. The promised functionality is an HTTP request library with some additional functions. On every usage, code secretly checks for the presence of specific fields in the response, and if they are found, their content is secretly executed.


---

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.


Campaign: 2026-08-reqcrypt


Reasons (based on the campaign):


 - backdoor

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/8ce81c3fe430b92ddda9512dd755648912396d2a/osv/malicious/pypi/requests-crypt/MAL-2026-14351.json))

## Paquetes afectados

- `requests-crypt` (pip), versiones afectadas: = 0.1.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-21T12:30:34Z
- Fuente: https://github.com/advisories/GHSA-cf52-hr54-m53p

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
