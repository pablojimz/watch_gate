# Aviso: Malicious code in sm-admin (npm) (GHSA-g8wg-mh5v-wf2r)

## Resumen

## Source: amazon-inspector (fa2741ebbd0df8c6f349a4d34361cc3d814fe878f3f4521fd771a855cfdc152b)
Package sm-admin@99.0.0 defines preinstall and postinstall lifecycle scripts that issue plain-HTTP GET requests to a hardcoded bare-IP endpoint at http://16.192.173.5/sm-admin/pre and http://16.192.173.5/sm-admin/post. Installing the package causes the installer host to contact this endpoint, revealing that the internal-sounding name 'sm-admin' resolved on that machine and disclosing the installer's source IP to the operator of that endpoint. The destination is a bare IPv4 over cleartext HTTP with no relationship to any publisher, and the elevated version number (99.0.0) together with the callback shape is characteristic of a dependency-confusion probe against a private-registry name. The endpoint is attacker-controlled and unauthenticated, so the response body served to preinstall/postinstall could change at any time.

## Source: ossf-package-analysis (80e0a34b4b727bd2f26180a0ef6bca6ca81e6dfa5b011ff320f07f37c2d9369c)
The OpenSSF Package Analysis project identified 'sm-admin' @ 99.0.1 (npm) as malicious.

It is considered malicious because:

- The package executes one or more commands associated with malicious behavior.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/69cf85db3ebafc0534169441a15154ec56e73b2b/osv/malicious/npm/sm-admin/MAL-2026-14393.json))

## Paquetes afectados

- `sm-admin` (npm), versiones afectadas: = 99.0.0
- `sm-admin` (npm), versiones afectadas: = 99.0.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-24T06:30:32Z
- Fuente: https://github.com/advisories/GHSA-g8wg-mh5v-wf2r

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
