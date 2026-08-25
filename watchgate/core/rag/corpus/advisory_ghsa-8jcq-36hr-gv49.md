# Aviso: Malicious code in amundi-compare (npm) (GHSA-8jcq-36hr-gv49)

## Resumen

## Source: amazon-inspector (0bc0f77ca83947d2af9978911d3a4da11af6a6a4773268f662291180c27b6f38)
amundi-compare@999.9.12 is published at an inflated version number consistent with dependency-confusion targeting of an internal package name. The package.json declares a preinstall hook (`node index.js`) that runs automatically on `npm install`. index.js collects hostname, OS user, home directory, current working directory, local IPv4 addresses, public egress IP (queried from api.ipify.org, icanhazip.com, and ifconfig.me), the DNS resolver IP and client subnet, and the parent project's package.json name/author/repository/homepage fields. The payload is transmitted through three parallel channels to the hardcoded callback host da51rv0hb2uc72tg4gvgdepinjcallbk1.oast.fun: an HTTP POST, an HTTPS POST to /poc/<uuid>, and a DNS covert channel that hex-encodes the JSON, splits it into <=60-character chunks, and emits each chunk as a subdomain label under the callback domain. The DNS channel is designed to bypass egress filters that block outbound HTTP. The package labels itself as authorized security research, but the callback host is not installer-configured and the parent project's metadata is captured without consent.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/e307a23db650fb76255155feb9c7f2fecd528fef/osv/malicious/npm/amundi-compare/MAL-2026-14390.json))

## Paquetes afectados

- `amundi-compare` (npm), versiones afectadas: = 999.9.12

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-24T06:30:34Z
- Fuente: https://github.com/advisories/GHSA-8jcq-36hr-gv49

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
