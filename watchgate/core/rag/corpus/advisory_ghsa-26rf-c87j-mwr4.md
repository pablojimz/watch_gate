# Aviso: Malicious code in sm-apikey-model (npm) (GHSA-26rf-c87j-mwr4)

## Resumen

## Source: amazon-inspector (d8e5a8bc4d985b445afbc71bd563bcee445381d2539a7110a0ca53d54b800367)
package.json declares preinstall and postinstall lifecycle scripts that invoke curl over plain HTTP to a hardcoded bare-IP endpoint (http://16.192.173.5/sm-apikey-model/pre and.../post). The path segment embeds the package name, so the operator of that endpoint receives a callback confirming each host that installed this specific package, along with the installer's source IP. The version number (99.0.0) and the dependency-confusion beacon shape are consistent with a namespace-squat reconnaissance package rather than a functional library.

## Source: ossf-package-analysis (58440b7c774647b07278e54b62e08591a1f106b1e0dfb2f597fd3663512ab427)
The OpenSSF Package Analysis project identified 'sm-apikey-model' @ 99.0.1 (npm) as malicious.

It is considered malicious because:

- The package executes one or more commands associated with malicious behavior.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/69cf85db3ebafc0534169441a15154ec56e73b2b/osv/malicious/npm/sm-apikey-model/MAL-2026-14394.json))

## Paquetes afectados

- `sm-apikey-model` (npm), versiones afectadas: = 99.0.0
- `sm-apikey-model` (npm), versiones afectadas: = 99.0.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-24T06:30:32Z
- Fuente: https://github.com/advisories/GHSA-26rf-c87j-mwr4

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
