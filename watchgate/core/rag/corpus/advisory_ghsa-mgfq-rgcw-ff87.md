# Aviso: Malicious code in rust-testing-utils (npm) (GHSA-mgfq-rgcw-ff87)

## Resumen

## Source: amazon-inspector (ee33bdedc7938508bcb50e053c441770948d3d69a51c5cab5d4280d84ceffa65)
The package impersonates the pino logger in its README, keywords, and API surface. index.js exports middleware that spawns lib/caller.js as a detached child process on invocation. caller.js reconstructs a hardcoded URL by base64-decoding a value stored under a fake `process.env.DEV_API_KEY` inside a fabricated `process` object, resolving to https://api.jsonstorage.net/v1/json/2ef8c758-a96f-459e-b036-b3b90379a165/f89e8264-86c2-4684-94da-c3f82d59370f. It fetches this URL with axios and passes the returned `cookie` field to `new Function.constructor("require", s)`, then invokes the resulting function with `require` as an argument, giving the remotely fetched code arbitrary execution with full module-loading capability in the consumer's process. The endpoint content is attacker-controlled and mutable, so the executed payload can change at any time without a package update. The base64-encoded URL, fabricated env-var names used to hide the destination, and pino-lookalike cover story are consistent with an intentional supply-chain attack rather than legitimate functionality.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/51911d234a84078e05bdf54c4b86161625e68d64/osv/malicious/npm/rust-testing-utils/MAL-2026-14374.json))

## Paquetes afectados

- `rust-testing-utils` (npm), versiones afectadas: = 2.3.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-23T03:35:01Z
- Fuente: https://github.com/advisories/GHSA-mgfq-rgcw-ff87

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
