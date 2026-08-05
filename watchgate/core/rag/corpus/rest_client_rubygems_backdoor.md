# Caso: rest-client (RubyGems, GHSA-333g-rpr4-7hxq)

## Resumen

En agosto de 2019, las versiones 1.6.10 a 1.6.13 de la gema `rest-client`
(cliente HTTP muy usado en Ruby) distribuidas en RubyGems.org incluían un
backdoor de ejecución remota de código insertado por un tercero tras
comprometer la cuenta del mantenedor. El aviso oficial también reporta que,
como parte del mismo incidente o de investigaciones relacionadas, se
retiraron total o parcialmente otras gemas menores (`cron_parser`,
`coin_base`, `blockchain_wallet`, `bitcoin_vanity`, `capistrano-colors`,
entre otras) — varias con nombres relacionados con criptomonedas.

## Vector de introducción

- Mismo patrón que `coa_rc_npm_maintainer_compromise.md`: compromiso de la
  cuenta del mantenedor en el registro del paquete (RubyGems), no del
  repositorio de código — sin ningún PR ni commit que revisar.
- La presencia de varias gemas con nombres relacionados con criptomonedas
  entre las afectadas/retiradas sugiere un objetivo específico: robo de
  credenciales o claves de wallets en máquinas de desarrolladores que
  trabajan con ese tipo de proyectos.
- Es uno de los primeros casos ampliamente documentados de este patrón
  (2019, antes que `event-stream`, `coa`/`rc` o `ctx`), por lo que sirve de
  referencia temprana de que el vector "cuenta de mantenedor comprometida
  en el registro del paquete" no es nuevo ni exclusivo de un ecosistema.

## Por qué es relevante para WatchGate

- Demuestra que este patrón (compromiso de cuenta en el registro, no en
  git) es transversal a lenguajes/ecosistemas: PyPI (`ctx`, `sympy-dev`),
  npm (`event-stream`, `coa`, `rc`), RubyGems (`rest-client`) — la
  arquitectura de WatchGate, agnóstica de lenguaje en el núcleo, debe
  asumir que este vector puede aparecer en cualquier gestor de paquetes que
  el proyecto use, no solo en el ecosistema "principal" del repositorio.
- Recomendación operativa citada en el propio aviso —rotar todos los
  secretos de cualquier máquina con el paquete instalado, no solo
  "desinstalar"— es coherente con tratar cualquier detección de este
  patrón como incidente de compromiso total, no como un hallazgo aislado.

Técnica MITRE ATT&CK relacionada: T1195.001 (Compromise Software
Dependencies and Development Tools).
