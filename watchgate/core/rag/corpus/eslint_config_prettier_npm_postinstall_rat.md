# Caso: eslint-config-prettier (npm, CVE-2025-54313) — troyano vía script postinstall

## Resumen

En julio de 2025 se descubrió que varias versiones de `eslint-config-prettier`
(más de 30 millones de descargas semanales) y paquetes relacionados del
mismo ecosistema (`eslint-plugin-prettier`, `synckit`, `@pkgr/core`,
`napi-postinstall`) habían sido publicadas con código malicioso embebido
tras el phishing de las credenciales de un mantenedor. Las versiones
afectadas incluían un script `postinstall` que, en sistemas Windows,
soltaba y ejecutaba un binario DLL (un troyano de acceso remoto conocido
como "Scavenger") usando `rundll32`.

## Vector de introducción

- Mismo patrón de acceso inicial que otros casos de este corpus (phishing
  dirigido al mantenedor con permisos de publicación) — no una
  vulnerabilidad técnica de npm ni del propio paquete.
- El vector de ejecución es específico y muy relevante para auditoría de
  PRs: un script `postinstall` en `package.json` se ejecuta
  **automáticamente en cuanto alguien instala el paquete** (`npm install`),
  sin ninguna acción explícita adicional — a diferencia de código de
  aplicación normal, que solo se ejecuta si el flujo del programa llega
  hasta él.
- El payload no era JavaScript ofuscado fácil de reconocer a simple vista:
  el script soltaba un fichero binario (`node-gyp.dll`, nombre elegido
  para camuflarse entre las herramientas de compilación nativa legítimas
  que sí usa el ecosistema npm) y lo ejecutaba con un binario del propio
  sistema operativo (`rundll32.exe`), evadiendo así firmas que solo buscan
  JavaScript sospechoso.

## Patrón a vigilar

Campo `scripts.postinstall`/`preinstall`/`prepare` nuevo o modificado en
`package.json`, o un binario nuevo sin justificación evidente en el
paquete.

Técnica MITRE ATT&CK relacionada: T1195.001 (Compromise Software
Dependencies and Development Tools), T1078 (Valid Accounts).
