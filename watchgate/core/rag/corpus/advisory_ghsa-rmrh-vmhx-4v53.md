# Aviso: Malicious code in js-soul (npm) (GHSA-rmrh-vmhx-4v53)

## Resumen

On module load, src/api/session-api.js reads../../../../public/logo.ico (a path outside the package), DES-decrypts the contents with the hardcoded key 'bf497c0b9cee', spawns a detached `node` child process via child_process.spawn with {detached:true}, and pipes the decrypted plaintext into the interpreter's stdin, executing arbitrary code at `import 'js-soul'`. The disguise of executable JavaScript as an image asset, the hardcoded DES key, and an unrelated 'ThetaSDK initialization error' catch-block string contradict the package's stated purpose as a session helper library and its README claim that nothing runs on import. Any code the attacker stages at the sibling path executes in the installer process with the installer's privileges.

## Paquetes afectados

- `js-soul` (npm), versiones afectadas: = 1.0.4

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-rmrh-vmhx-4v53

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `js-soul`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
