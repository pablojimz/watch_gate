# Caso: coa + rc (npm, GHSA-73qr-pfmq-6rp8 / GHSA-g2q5-5433-rhrf)

## Resumen

El 4 de noviembre de 2021, dos paquetes npm populares y sin relación
funcional entre sí —`coa` (parser de argumentos de línea de comandos) y
`rc` (carga de configuración)— publicaron simultáneamente versiones con
código malicioso. Ambos son dependencias transitivas extremadamente
comunes (`rc` en particular es una dependencia casi universal a través de
otros paquetes muy usados), lo que hizo que miles de proyectos instalaran
las versiones comprometidas simplemente al ejecutar `npm install` durante
esa ventana de tiempo, sin ningún cambio en su propio código.

## Vector de introducción

- Compromiso de las **cuentas de npm de los mantenedores**, no del código
  fuente en ningún repositorio git — los cambios maliciosos no pasaron por
  ninguna revisión de PR porque se publicaron directamente al registro,
  sin ningún commit visible que los preceda.
- El aviso oficial de GitHub advierte tratar cualquier máquina con estos
  paquetes instalados como **completamente comprometida**: el payload no
  se limitaba a robar un dato concreto, sino que buscaba control total.
- El hecho de que fueran dos paquetes distintos, sin relación entre sí,
  comprometidos el mismo día, sugiere una campaña coordinada o una fuente
  común de compromiso (p. ej. credenciales de npm reutilizadas o robadas de
  varios mantenedores a la vez).

## Por qué es relevante para WatchGate

- Es el caso que mejor ilustra el límite de "revisar el diff de un PR": si
  el compromiso ocurre en la publicación al registro (`npm publish`) y no
  en un commit al repositorio, ninguna herramienta que analice diffs de
  PRs lo verá — mismo límite ya documentado en el caso SolarWinds, aquí a
  nivel de un solo mantenedor en vez de infraestructura corporativa.
- Refuerza por qué la consulta en vivo a OSV de las dependencias nuevas
  (`gather_dependency_findings`) es una capa de defensa complementaria y
  necesaria: es la única señal disponible cuando el ataque nunca pasó por
  un diff de código revisable.
- Dos paquetes de propósito completamente distinto comprometidos el mismo
  día es en sí mismo un patrón: cuando aparece, conviene tratar cualquier
  otra dependencia nueva del mismo periodo con sospecha reforzada.

Técnica MITRE ATT&CK relacionada: T1195.001 (Compromise Software
Dependencies and Development Tools).
