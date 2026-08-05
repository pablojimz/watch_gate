# MITRE ATT&CK T1195.001 — Compromise Software Dependencies and Development Tools

## Descripción

Sub-técnica de T1195 (Supply Chain Compromise), distinta de T1195.002 ya
cubierta en este corpus: mientras T1195.002 es la manipulación de la propia
aplicación/producto, T1195.001 es específicamente la manipulación de sus
**dependencias y herramientas de desarrollo** — paquetes de `pip`/`npm`
usados como bloques de construcción, no el software final en sí. MITRE cita
explícitamente tres patrones:

- Manipular paquetes populares usados como dependencias para propagar
  código malicioso a todo lo que dependa de ellos.
- **Reclamar paquetes abandonados** ("revival hijacking"): un paquete
  eliminado o desatendido puede volver a registrarse bajo el mismo nombre
  por un actor distinto al original.
- *Typosquatting* / confusión de nombres: nombres parecidos a paquetes
  populares para engañar a quien instala.

MITRE también señala explícitamente los componentes de pipelines CI/CD
(GitHub Actions entre ellos) como objetivo: comprometer una sola Action
compartida por muchos repositorios puede propagar el compromiso a todos
ellos a la vez ("gusano" de Actions).

## Casos de este corpus que son ejemplos directos de esta sub-técnica

- `event_stream_flatmap_stream_npm.md` — dependencia transitiva nueva y sin
  reputación añadida a un paquete popular desatendido.
- `coa_rc_npm_maintainer_compromise.md`, `rest_client_rubygems_backdoor.md`
  — compromiso de la cuenta del mantenedor en el registro del paquete.
- `pypi_ctx_env_exfiltration.md` — dominio de contacto expirado y
  reclamado, mismo patrón de "reclamar lo abandonado" que MITRE describe
  para paquetes.
- `dependency_confusion.md` (incluye el caso real `sympy-dev`) —
  *typosquatting* de un paquete popular.
- `ultralytics_pypi_release_compromise.md` — compromiso del propio
  artefacto de dependencia publicado, no del código fuente.

## Por qué es relevante para WatchGate

- Es la sub-técnica que mejor describe, con una sola etiqueta, el propósito
  concreto de `gather_dependency_findings`/`lookup_package_registry`: no
  se está protegiendo el código propio del proyecto, sino la cadena de
  **dependencias que ese código declara usar**.
- La mención explícita de GitHub Actions como vector encaja con
  `prt_scan.md` y el caso de prueba `github-actions-secret-leak` — confirma
  que no es un vector hipotético, MITRE lo documenta como patrón activo y
  citado (campaña de "gusano" de GitHub Actions, 2023).
