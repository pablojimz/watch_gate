# Aviso: Malicious code in scrambleeer (PyPI) (GHSA-jx7v-9c55-jw2v)

## Resumen

## Source: kam193 (52d5b1e99e57b038247cf3b7f86a7514e75275a095ca3f3cf044d80cbe999472)
When using the provided library, the code starts a reverse shell to a hardcoded location.


---

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.


Campaign: 2026-08-scrambleeer


Reasons (based on the campaign):


 - The package contains code to create a reverse shell, allowing an attacker to execute any commands on the victim's machine.


 - action-hidden-in-lib-usage

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/03e1016b4270e6fe79c7cdc1288ba6dc9bbeccd0/osv/malicious/pypi/scrambleeer/MAL-2026-14350.json))

## Paquetes afectados

- `scrambleeer` (pip), versiones afectadas: = 0.1.0
- `scrambleeer` (pip), versiones afectadas: = 0.1.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-21T12:30:35Z
- Fuente: https://github.com/advisories/GHSA-jx7v-9c55-jw2v

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
