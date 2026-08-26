# Aviso: Malicious code in scrambleeeer (PyPI) (GHSA-xw2j-24j3-3282)

## Resumen

When using the provided library, the code starts a reverse shell to a hardcoded location.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-08-scrambleeer

Reasons (based on the campaign):

 - The package contains code to create a reverse shell, allowing an attacker to execute any commands on the victim's machine.

 - action-hidden-in-lib-usage

## Paquetes afectados

- `scrambleeeer` (pip), versiones afectadas: = 0.1.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-22T12:30:27Z
- Fuente: https://github.com/advisories/GHSA-xw2j-24j3-3282

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `scrambleeeer`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
