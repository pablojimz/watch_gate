# Aviso: Malicious code in houdus (PyPI) (GHSA-frjq-w86w-r3gr)

## Resumen

During import, package loads code disguised as ".wav" file. It performs extensive fingerprinting against sandboxes, and finally downloads and executes heavily obfuscated code. The remote code tries once more to avoid sandbox execution, establishes persistence via scheduled tasks and executes shellcode. Malicious code targets only Windows.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-09-houdus

Reasons (based on the campaign):

 - obfuscation

 - Downloads and executes a remote malicious script.

 - The package contains code to detect if it is running in a sandbox environment.

 - persistence

 - shellcode

## Paquetes afectados

- `houdus` (pip), versiones afectadas: = 1.0.0
- `houdus` (pip), versiones afectadas: = 1.0.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-05T00:31:08Z
- Fuente: https://github.com/advisories/GHSA-frjq-w86w-r3gr

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `houdus`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
