# Aviso: Malicious code in hatdhat-testkit (npm) (GHSA-3ghm-p4g2-9r6p)

## Resumen

## Source: amazon-inspector (83b6e58e31221d5d14386a193ab49381950bb01307ac4fb4d7e5c30d246046d9)
Package presents itself as a pino-style logging utility but its middleware entrypoint (index.js) spawns lib/caller.js as a detached Node process. caller.js contains a fake `process` object whose `env.DEV_API_KEY`, `env.DEV_SECRET_KEY`, and `env.DEV_SECRET_VALUE` are base64 strings that decode to the URL https://api.jsonstorage.net/v1/json/2ef8c758-a96f-459e-b036-b3b90379a165/f89e8264-86c2-4684-94da-c3f82d59370f, the request header name `x-secret-key`, and its value. The loader GETs that mutable anonymous JSON blob and executes the response's `cookie` field via `new Function.constructor('require', s)(require)` with retry, granting the remote payload full Node capabilities including require(). The destination is unrelated to the advertised logging purpose and the URL/header are obfuscated to evade inspection.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/51911d234a84078e05bdf54c4b86161625e68d64/osv/malicious/npm/hatdhat-testkit/MAL-2026-14373.json))

## Paquetes afectados

- `hatdhat-testkit` (npm), versiones afectadas: = 3.2.14

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-23T03:35:01Z
- Fuente: https://github.com/advisories/GHSA-3ghm-p4g2-9r6p

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
