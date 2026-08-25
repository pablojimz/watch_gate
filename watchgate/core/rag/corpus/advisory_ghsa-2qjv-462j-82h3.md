# Aviso: Malicious code in fund-calculator (npm) (GHSA-2qjv-462j-82h3)

## Resumen

## Source: amazon-inspector (52c5f9f0536151a173aa211b9b5f2972e68aee3043132adccdb3695947b16672)
Package declares a preinstall script (`node index.js`) that fires unconditionally on `npm install`. index.js reads installer-side identifiers via `os.hostname()`, `os.userInfo()`, `INIT_CWD`, home directory, and the parent project's package.json (name/author/repository/homepage), and additionally resolves the installer's public IP via https requests to api.ipify.org, icanhazip.com, and ifconfig.me. The collected data is transmitted to the hardcoded callback `da51rv0hb2uc72tg4gvgdepinjcallbk1.oast.fun` over three channels: HTTP POST to port 80, HTTPS POST to port 443 on path `/poc/${uuid}`, and DNS resolution of hex-encoded payload chunks (Buffer.from(body).toString('hex') split into 60-character labels) emitted as subdomains under the callback host to bypass egress filters that permit DNS but block outbound HTTP. The 999.9.12 version number and package name are consistent with a dependency-confusion name-squat designed to win resolution against a private internal package of the same name.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/e307a23db650fb76255155feb9c7f2fecd528fef/osv/malicious/npm/fund-calculator/MAL-2026-14391.json))

## Paquetes afectados

- `fund-calculator` (npm), versiones afectadas: = 999.9.12

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-24T06:30:34Z
- Fuente: https://github.com/advisories/GHSA-2qjv-462j-82h3

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
