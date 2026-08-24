# Aviso: Malicious code in rc4-secure (PyPI) (GHSA-q3mh-hmf4-7c8m)

## Resumen

## Source: kam193 (c00d4194b32151e318678fb20166e9023d74acbed43e4a9d82f7834569cb73bd)
Package silently installs a remote executable in a way that is intentionally hidden from the user. During analysis, the code was downloading a legitimate software unrelated to provided functionality, suggesting it is a research-like demonstration.


---

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.


Campaign: 2026-08-rc4-secure


Reasons (based on the campaign):


 - Downloads and executes a remote executable.


 - modify-system-without-consent


 - action-hidden-in-lib-usage

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/95a79a3d6ded5111b034d760f9f83c88ad44eed5/osv/malicious/pypi/rc4-secure/MAL-2026-14306.json))

## Paquetes afectados

- `rc4-secure` (pip), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-19T21:30:25Z
- Fuente: https://github.com/advisories/GHSA-q3mh-hmf4-7c8m

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
