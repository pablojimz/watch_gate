# Aviso: Malicious code in ecobee-api (npm) (GHSA-43wq-pqvv-wrfp)

## Resumen

On `npm install`, ecobee-api runs `node beacon.js` via its postinstall lifecycle script. The beacon issues an HTTP GET to the hardcoded bare-IP endpoint http://169.58.96.170:9001/cb, passing the installer's hostname (os.hostname()) and the package name as query parameters. The package ships no functional library code — package.json declares an UNLICENSED 'Utility package' with a name resembling the Ecobee vendor, and the only substantive shipped file is the beacon. This is the shape of a dependency-confusion / typosquat recon beacon: it confirms install-time code execution on the victim host and identifies the host to the operator of 169.58.96.170 over plain HTTP.

## Paquetes afectados

- `ecobee-api` (npm), versiones afectadas: = 0.0.2

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-43wq-pqvv-wrfp

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `ecobee-api`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
