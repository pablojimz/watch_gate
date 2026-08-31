# Aviso: Malicious code in calcboxlite (PyPI) (GHSA-q2qg-w4f2-8v29)

## Resumen

setup.py and calcboxlite/__init__.py both invoke a top-level `_report()` function that reads `getpass.getuser()` and `socket.gethostname()` and POSTs them as JSON to a hardcoded remote collector at https://k4m2qhx7ptv9nzcr3bwe8syd6ljfa0gu1.oast.invalid/collect. The beacon fires automatically on `pip install` and again on every `import calcboxlite`, so consumers in sandboxed builds, CI runners, REPLs, or downstream libraries all transmit installer identity to the endpoint. The destination host is unrelated to any advertised calculator functionality and is characteristic of an out-of-band interaction collector used for identifying vulnerable installers.

## Paquetes afectados

- `CalcBoxLite` (pip), versiones afectadas: = 1.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-28T21:31:06Z
- Fuente: https://github.com/advisories/GHSA-q2qg-w4f2-8v29

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `CalcBoxLite`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
