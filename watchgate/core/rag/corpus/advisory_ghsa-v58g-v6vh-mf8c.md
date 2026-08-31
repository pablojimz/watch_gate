# Aviso: Malicious code in zenntechinc-cli (npm) (GHSA-v58g-v6vh-mf8c)

## Resumen

The npm package ships an obfuscated payload appended to templates/backend/.eslintrc.js, after a legitimate-looking ESLint config. The payload uses obfuscator.io-style string-array indirection (rotating _0x12f0() table, hex-named identifiers) to conceal Ethereum JSON-RPC endpoints (eth.drpc.org, ethereum.publicnode.com, blastapi.io, blockscout) and an Etherscan-style txlist indexer path. It queries the latest transaction from a hardcoded sender address (0xa322e5f3...9adc2490ef), decodes two IPv4 C2 addresses from the transaction's `to` field, fetches an XOR-encoded payload from those IPs, and executes it via eval() and spawn('node', ['-e', payload], {detached:true}).unref(). The CLI's `new` subcommand in bin/zenntechinc.js recursively copies the entire templates/backend tree — including the malicious.eslintrc.js — into the user-specified target directory via copyDirectory(), with no filtering. Any subsequent editor open, ESLint invocation, or lint script run inside the generated project loads this.eslintrc.js and triggers the blockchain-resolved remote code execution with full developer privileges. The CLI's advertised purpose (backend scaffolding) is the delivery vector for the RCE payload into the installer's workspace.

## Paquetes afectados

- `zenntechinc-cli` (npm), versiones afectadas: = 1.6.6
- `zenntechinc-cli` (npm), versiones afectadas: = 1.6.4

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-26T15:31:42Z
- Fuente: https://github.com/advisories/GHSA-v58g-v6vh-mf8c

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `zenntechinc-cli`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
