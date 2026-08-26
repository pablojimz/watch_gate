# Aviso: Malicious code in secretkey-2fa (npm) (GHSA-53gx-pc7p-ww5j)

## Resumen

Package presents itself as a zero-dependency TOTP library but its postinstall hook (`node lib/core.js`) and its advertised `validateSecret` API both trigger a stealer pipeline in lib/core.js. The script reads Minecraft launcher credential stores (launcher_accounts*.json,.lunarclient/settings/game/accounts.json, gg.essential.mod/microsoft_accounts.json, CurseForge/storage.json, ModrinthApp files, launcher_msa_credentials_microsoft_store.bin), extracts access and refresh tokens, and exchanges MSA refresh tokens through login.live.com, xboxlive and api.minecraftservices.com for fresh Minecraft SSID JWTs. It also enumerates Discord (stable/canary/ptb/development) and Chromium-family (Chrome/Edge/Brave/Opera/Opera GX) Local Storage leveldb files, invokes PowerShell + DPAPI `ProtectedData::Unprotect` to recover each browser's os_crypt encrypted_key, AES-256-GCM decrypts token blobs, validates them against the Discord API, and multipart-POSTs valid tokens to a hardcoded attacker webhook. A separate routine (`_installMod`) locates every Minecraft mods/ directory (.minecraft/mods, ModrinthApp profiles, Lunar offline versions) and writes a JAR fetched from `github.com/ghysghqgHUJ/.jar/releases/download/v1.0.0/fabric-api-boost-1.0.0.jar` into each, so the payload loads on the next Minecraft launch. The exfil URL, PowerShell command strings, DPAPI class names, `child_process`, and the Discord API host are stored as XOR-0x3F byte arrays and reconstructed at runtime by `_x = a => Buffer.from(a.map(b => b ^ 0x3F))`. The stealer is reachable via two paths: the postinstall lifecycle script and a `setImmediate(() => _run())` inside the exported `validateSecret` function, so an `--ignore-scripts` install followed by ordinary library use still detonates it.

## Paquetes afectados

- `secretkey-2fa` (npm), versiones afectadas: = 1.0.0
- `secretkey-2fa` (npm), versiones afectadas: = 1.0.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-53gx-pc7p-ww5j

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `secretkey-2fa`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
