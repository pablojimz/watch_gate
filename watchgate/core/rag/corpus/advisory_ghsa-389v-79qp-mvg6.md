# Aviso: Malicious code in tailwind-contact-forms (npm) (GHSA-389v-79qp-mvg6)

## Resumen

tailwind-contact-forms ships src/index.js containing the legitimate @tailwindcss/forms plugin source concatenated with an obfuscator.io-style payload (rotating 328-entry string array _0x303e with decoder _0x1574, ~1300 deobfuscation transforms). The obfuscated section decodes to host-reconnaissance strings ('hostname', 'Win64; x64', 'process.env') and to network destinations targeting Ethereum RPC / block-explorer infrastructure ('h.drpc.org', 'pc.io/eth', an 'stapi.io' host, 'ut.com/api', and Etherscan-style query parameters '?module=account&action=txlist&', 'nonce', 'startbloc'). Because src/index.js is the package's main entry, the payload executes on require() in any project that installs this package. The package manifest declares repository = https://github.com/tailwindlabs/tailwindcss-forms (the real Tailwind Labs upstream, whose actual npm name is @tailwindcss/forms) while publishing under the unrelated name tailwind-contact-forms, impersonating the upstream to lure developers who mistype the real package. A CSS/Tailwind plugin has no functional reason to run obfuscated code, read host identifiers and process.env, or contact Ethereum RPC and block-explorer APIs at import time.

## Paquetes afectados

- `tailwind-contact-forms` (npm), versiones afectadas: = 0.5.12

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-04T09:32:12Z
- Fuente: https://github.com/advisories/GHSA-389v-79qp-mvg6

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `tailwind-contact-forms`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
