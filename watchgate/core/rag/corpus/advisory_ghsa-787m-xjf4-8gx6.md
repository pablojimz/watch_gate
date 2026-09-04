# Aviso: Malicious code in claude-channel-discord (npm) (GHSA-787m-xjf4-8gx6)

## Resumen

claude-channel-discord@9.9.9 is a dependency-confusion probe. package.json declares preinstall and postinstall hooks (`node index.js --save-prod`) and a main entry that both execute index.js, which reads os.hostname() and issues a GET to https://eo8f3m3ho26a0nm.m.pipedream.net/claude-channel-discord?h=${hostname}. The beacon fires automatically on `npm install` and again on `require()` of the package. The package has an empty description, an implausibly high 9.9.9 version, a self-referential dependency, and a name shaped to collide with an internal or typoed identifier — the canonical dependency-confusion reconnaissance pattern, leaking the installer's host identifier to an author-controlled Pipedream collection endpoint.

## Paquetes afectados

- `claude-channel-discord` (npm), versiones afectadas: = 9.9.9

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T09:32:12Z
- Fuente: https://github.com/advisories/GHSA-787m-xjf4-8gx6

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `claude-channel-discord`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
