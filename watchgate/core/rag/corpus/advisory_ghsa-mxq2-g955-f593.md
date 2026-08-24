# Aviso: Malicious code in sm-payment (npm) (GHSA-mxq2-g955-f593)

## Resumen

## Source: amazon-inspector (926b17cedd788f5f626b3c4001ca9f1b9572abe425b87d40d6f03814d211e3e7)
package.json declares preinstall and postinstall lifecycle scripts that curl a hardcoded bare IP over plain HTTP (http://16.192.173.5/sm-payment/pre and.../post) automatically on npm install. The package has no build or native-addon purpose that would justify contacting a bare IP at install time; the callbacks fire unsolicited on every install and signal to the operator of that endpoint that the installer's host executed the package. The shape (bare IP, plain HTTP, unrelated to any documented package function, fired from both preinstall and postinstall) is consistent with dependency-confusion / namesquat reconnaissance beacons.

## Source: ossf-package-analysis (9608faee43a02423aaf69985bd63b5c9bd188dbfeccc359fb9de20cfdf432a7e)
The OpenSSF Package Analysis project identified 'sm-payment' @ 99.0.1 (npm) as malicious.

It is considered malicious because:

- The package executes one or more commands associated with malicious behavior.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/69cf85db3ebafc0534169441a15154ec56e73b2b/osv/malicious/npm/sm-payment/MAL-2026-14399.json))

## Paquetes afectados

- `sm-payment` (npm), versiones afectadas: = 99.0.1
- `sm-payment` (npm), versiones afectadas: = 99.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-24T06:30:33Z
- Fuente: https://github.com/advisories/GHSA-mxq2-g955-f593

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
