# Aviso: Malicious code in solidity-testing-utils (npm) (GHSA-g5g4-w6x5-58j4)

## Resumen

## Source: amazon-inspector (7a7ffd7dfab8f1c168ceb5ae9b26f4221e912d2a444afe029b83b1f214cf3bd8)
Package presents itself as a chai/solidity testing helper and pino-style logger, but its exported middleware factory in index.js silently spawns lib/caller.js via child_process.spawn('node', [...], { detached: true, stdio: 'ignore' }) followed by child.unref(). lib/caller.js base64-decodes a hardcoded URL to https://api.jsonstorage.net/v1/json/2ef8c758-a96f-459e-b036-b3b90379a165/f89e8264-86c2-4684-94da-c3f82d59370f, performs an axios GET with a hardcoded 'x-secret-key' header, reads the.data.cookie field from the response, and passes it to new Function.constructor('require', s)(require), giving the returned JavaScript full arbitrary code execution with require access in the installer's Node.js process. The destination is an attacker-controlled mutable JSON blob; the fetched payload can be swapped at any time. Package name and README do not correspond to the actual behavior.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/51911d234a84078e05bdf54c4b86161625e68d64/osv/malicious/npm/solidity-testing-utils/MAL-2026-14375.json))

## Paquetes afectados

- `solidity-testing-utils` (npm), versiones afectadas: = 1.2.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-23T03:35:01Z
- Fuente: https://github.com/advisories/GHSA-g5g4-w6x5-58j4

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
