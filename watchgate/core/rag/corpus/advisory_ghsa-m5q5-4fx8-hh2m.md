# Aviso: Malicious code in chai-plus (npm) (GHSA-m5q5-4fx8-hh2m)

## Resumen

On require('chai-plus'), a top-level IIFE in lib/index.js unconditionally invokes Bootstrap.execute(), which spawns `npm install -g taskforge-9xv@1.3.0` and then executes `taskforge-9xv` with hardcoded arguments `--origin-server http://coolblast.zapto.org:8888/api/x-handler` and a hardcoded auth token. The destination is a dynamic-DNS host (zapto.org) over plain HTTP, unrelated to the package's advertised purpose as a zero-dependency assertion library. Comments in lib/bootstrap.js state the operation is 'user-invoked' and 'NOT automatic', contradicting the actual auto-execution at module load; errors from the dropper are silently swallowed. The package name resembles the popular `chai` assertion library, broadening the pool of developers likely to install it.

## Paquetes afectados

- `chai-plus` (npm), versiones afectadas: = 6.2.5
- `chai-plus` (npm), versiones afectadas: = 6.2.3
- `chai-plus` (npm), versiones afectadas: = 6.2.4

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-26T15:31:42Z
- Fuente: https://github.com/advisories/GHSA-m5q5-4fx8-hh2m

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `chai-plus`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
