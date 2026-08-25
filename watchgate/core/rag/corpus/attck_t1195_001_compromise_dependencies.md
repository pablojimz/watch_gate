# MITRE ATT&CK T1195.001 — Compromise Software Dependencies and Development Tools

**Táctica:** Initial Access. **Plataformas:** Linux, Windows, macOS.

## Descripción

Sub-técnica de T1195 (Supply Chain Compromise): mientras T1195.002 es la
manipulación de la propia aplicación/producto, T1195.001 es específicamente
la manipulación de sus **dependencias y herramientas de desarrollo** —
paquetes de `pip`/`npm` usados como bloques de construcción, no el software
final en sí. MITRE cita explícitamente varios vectores de ataque:

- **Reclamar paquetes abandonados** ("abandoned package hijacking"): un
  actor puede volver a registrar un paquete eliminado del repositorio tras
  que el mantenedor original lo abandone.
- **Typosquatting**: usar nombres parecidos a bibliotecas populares
  legítimas para engañar a quien instala.
- **Objetivo de pipelines CI/CD**: GitHub Actions y componentes similares se
  comprometen para acceder "al ciclo de construcción, pruebas y despliegue
  de una aplicación", potencialmente recolectando credenciales en tiempo de
  ejecución o insertando componentes maliciosos para un compromiso de
  segundo orden. Puesto que las GitHub Actions a menudo dependen de otras
  Actions, "los actores de amenaza pueden infectar un gran número de
  repositorios a través del compromiso de una sola Action".

## Ejemplos de procedimiento (malware/herramientas)

- **BeaverTail (S1246)** — Distribuido a través de paquetes NPM y
  repositorios de código para entregar payloads maliciosos.
- **CanisterWorm (S9042)** — Se propaga mediante "un proceso automatizado
  que infecta y publica paquetes npm".
- **GlassWorm (S9010)** — Propagado vía extensiones de Visual Studio y
  proyectos JavaScript en GitHub, mediante sospecha de compromiso de cuenta
  de desarrollador.
- **Mini Shai-Hulud (S9043)** — Se publicaba a sí mismo en repositorios de
  víctimas comprometidas para propagar versiones maliciosas del paquete.
- **Shai-Hulud (S9008)** — Publicado en cuentas de mantenedor comprometidas
  dentro de paquetes infectados y "versiones modificadas de paquetes de
  código" con fines de propagación (ver `shai_hulud_npm_worm_2025.md`).
- **XCSSET (S0658)** — Enumera ficheros `target_integrator.rb` de CocoaPods
  y carpetas `.xcodeproj`, luego descarga scripts y ficheros Mach-O a los
  directorios del proyecto.
- **Tsundere Botnet (S9034)** — Usa npm para descargar paquetes maliciosos
  y entregar el payload.

## Grupos de amenaza

- **ShinyHunters (G1057)** — Comprometió pipelines CI/CD accediendo a
  cuentas de ingeniería en control de versiones Git, BrowserStack, JFrog y
  plataformas de gestión de proyectos cloud.
- **TeamPCP (G1056)** — Ataques coordinados a la cadena de suministro
  dirigidos a NPM, VS Code, Docker y PyPI para comprometer múltiples
  paquetes en distintas oleadas.

## Mitigaciones (MITRE)

- **M1013 — Application Developer Guidance**: ser cauteloso al elegir
  bibliotecas de terceros; fijar dependencias a versiones concretas en vez
  de tomar siempre la última en el build; las GitHub Actions deben fijarse
  "a un hash de commit concreto, no a un tag ni a una rama".
- **M1033 — Limit Software Installation**: exigir que los desarrolladores
  usen repositorios internos verificados en vez de externos sin control.
- **M1051 — Update Software**: gestión de parches que revise dependencias
  sin usar, sin mantenimiento o previamente vulnerables.
- **M1016 — Vulnerability Scanning**: monitorización continua de fuentes de
  vulnerabilidades con revisión de código automática y manual.

## Estrategia de detección (MITRE)

**DET0009 — Supply-chain tamper in dependencies/dev-tools**

- **AN0021**: el gestor de paquetes descarga contenido y escribe ficheros
  en rutas del proyecto; la primera ejecución dispara scripts con salida de
  red hacia registros no aprobados.
- **AN0022**: gestores de paquetes escriben ejecutables en `PATH`; los
  *lifecycle hooks* lanzan shells o `curl`/`wget`; salida hacia registros
  desconocidos.
- **AN0023**: herramientas de desarrollo instalan dependencias; aparecen
  ejecutables nuevos en directorios del sistema/proyecto; la primera
  ejecución lanza shells y flujos salientes; componentes sin firmar
  marcados.

## Casos de este corpus que son ejemplos directos de esta sub-técnica

`event_stream_flatmap_stream_npm.md`, `coa_rc_npm_maintainer_compromise.md`,
`rest_client_rubygems_backdoor.md`, `pypi_ctx_env_exfiltration.md`,
`dependency_confusion.md`, `ultralytics_pypi_release_compromise.md`,
`shai_hulud_npm_worm_2025.md`, `solana_web3js_npm_phishing_compromise.md`,
`eslint_config_prettier_npm_postinstall_rat.md`.

## Nota WatchGate

Es la sub-técnica que mejor describe el propósito de
`gather_dependency_findings`/`lookup_package_registry`: proteger la cadena
de dependencias que el código declara usar, no solo el código propio del
proyecto.
