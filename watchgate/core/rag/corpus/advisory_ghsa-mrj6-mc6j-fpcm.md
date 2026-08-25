# Aviso: Malicious code in stillm4ddpocs-rtest-alpha (npm) (GHSA-mrj6-mc6j-fpcm)

## Resumen

## Source: amazon-inspector (47545f800dcb07213863afb8beab283755fb596ea7d5d478b60e4ff449453839)
package.json declares a preinstall hook that runs index.js on npm install. index.js collects the installer's local IPv4, public IP (via https://api.ipify.org, https://icanhazip.com, https://ifconfig.me), DNS-resolver IP, hostname, OS username, home directory, cwd, and the parent project's package.json name/author/repository/homepage, then transmits the JSON to the hardcoded callback da51rv0hb2uc72tg4gvgdepinjcallbk1.oast.fun via three channels: HTTP POST on:80, HTTPS POST on:443, and DNS TXT queries whose labels carry the hex-encoded payload split into 60-character chunks. The DNS covert channel and hex chunking are structured to bypass egress filtering that blocks outbound HTTP. The package's self-description as 'authorised security research' does not gate execution; any project that resolves this name at install time transmits the data without consent. The 999.9.9 version and lure name are consistent with a dependency-confusion probe.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/51911d234a84078e05bdf54c4b86161625e68d64/osv/malicious/npm/stillm4ddpocs-rtest-alpha/MAL-2026-14377.json))

## Paquetes afectados

- `stillm4ddpocs-rtest-alpha` (npm), versiones afectadas: = 999.9.10
- `stillm4ddpocs-rtest-alpha` (npm), versiones afectadas: = 999.9.9

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-23T03:35:01Z
- Fuente: https://github.com/advisories/GHSA-mrj6-mc6j-fpcm

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
