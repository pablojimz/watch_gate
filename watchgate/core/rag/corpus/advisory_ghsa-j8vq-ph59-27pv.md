# Aviso: Malicious code in stillm4ddpocs-rtest-bravo (npm) (GHSA-j8vq-ph59-27pv)

## Resumen

## Source: amazon-inspector (15e4272ba48bc8a81c8a76e7948aed6974b40956c151f05a613456e92690f5f2)
package.json declares scripts.preinstall = 'node index.js', so npm install auto-executes index.js. The script collects hostname, username, home directory, local IPv4, INIT_CWD, and the public egress IP (queried from api.ipify.org, icanhazip.com, and ifconfig.me), and reads the consuming project's package.json (INIT_CWD/package.json) to extract name, author, repository, and homepage — identifying which internal package name resolved to this public package. The payload is transmitted to the hardcoded collector da51rv0hb2uc72tg4gvgdepinjcallbk1.oast.fun via HTTPS POST to /poc/<uuid> and, in parallel, hex-encoded and chunked into DNS labels (`<idx>-<chunk>.u-<uuid>.<callback>`) resolved via dns.resolve, providing a fallback exfiltration channel when outbound HTTP is filtered. The package's self-description as a dependency-confusion research PoC does not change the behavior: installer host and parent-project identifiers are shipped to a third-party Interactsh collector without installer consent.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/51911d234a84078e05bdf54c4b86161625e68d64/osv/malicious/npm/stillm4ddpocs-rtest-bravo/MAL-2026-14378.json))

## Paquetes afectados

- `stillm4ddpocs-rtest-bravo` (npm), versiones afectadas: = 999.9.10
- `stillm4ddpocs-rtest-bravo` (npm), versiones afectadas: = 999.9.9

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-23T03:35:01Z
- Fuente: https://github.com/advisories/GHSA-j8vq-ph59-27pv

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
