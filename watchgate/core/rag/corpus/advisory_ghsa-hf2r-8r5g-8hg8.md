# Aviso: Malicious code in uvhttp-custom (PyPI) (GHSA-hf2r-8r5g-8hg8)

## Resumen

During installation, obfuscated code downloads and executes an executable. It appears to be a game launcher.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-09-uvhttp-custom

Reasons (based on the campaign):

 - The package overrides the install command in setup.py to execute malicious code during installation.

 - Downloads and executes a remote executable.

 - obfuscation

## Paquetes afectados

- `uvhttp-custom` (pip), versiones afectadas: = 1.7.9
- `uvhttp-custom` (pip), versiones afectadas: = 1.8.1
- `uvhttp-custom` (pip), versiones afectadas: = 1.9.9

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-03T18:31:17Z
- Fuente: https://github.com/advisories/GHSA-hf2r-8r5g-8hg8

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `uvhttp-custom`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
