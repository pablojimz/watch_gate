# Caso: event-stream / flatmap-stream (npm, GHSA-mh6f-8j2x-4483)

## Resumen

En noviembre de 2018, un usuario se ofreció como voluntario para mantener
`event-stream`, un paquete npm muy popular (más de 1,9 millones de
descargas semanales en su momento) cuyo autor original ya no tenía tiempo
de mantenerlo. Una vez con acceso de publicación, añadió como dependencia
`flatmap-stream`, un paquete nuevo y sin historial, publicado por el mismo
actor, que contenía código malicioso dirigido específicamente a robar
carteras de Bitcoin de aplicaciones que dependían (directa o
transitivamente) de `event-stream`, en particular la app de criptomonedas
Copay.

## Vector de introducción

- No fue un ataque técnico contra la infraestructura de npm: fue **ingeniería
  social contra el propio proceso de mantenimiento** — ofrecerse como
  voluntario para un paquete popular y desatendido es en sí mismo un vector
  de ataque a la cadena de suministro, sin necesitar ninguna vulnerabilidad.
- El payload no vivía en `event-stream` directamente, sino en una
  **dependencia nueva y transitiva** (`flatmap-stream`) sin descargas ni
  reputación previas — invisible a quien solo auditara el propio
  `event-stream` sin mirar sus dependencias nuevas.
- El código malicioso estaba ofuscado y solo se activaba si detectaba que el
  paquete que lo incluía transitivamente era la aplicación específica que
  el atacante quería atacar (Copay), evitando activarse en la inmensa
  mayoría de instalaciones y dificultando su detección.

## Por qué es relevante para WatchGate

- Caso de referencia para por qué `detect_new_python_dependencies` /
  `gather_dependency_findings` importan tanto como el análisis del propio
  código: el paquete "conocido y confiado" (`event-stream`) no cambió su
  comportamiento directamente — el riesgo entró por una dependencia nueva
  añadida a un paquete ya establecido.
- La reputación heredada de un paquete popular no protege frente a un
  cambio de mantenedor: un nuevo mantenedor con buenas intenciones
  aparentes (resolver un paquete desatendido) es un vector de confianza tan
  válido como cualquier otro para un atacante paciente.
- Técnica MITRE ATT&CK relacionada: T1195.001 (Compromise Software
  Dependencies and Development Tools).
