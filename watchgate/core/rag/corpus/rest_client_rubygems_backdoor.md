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

## Patrón a vigilar

Compromiso de cuenta en el registro del paquete (no en git) — patrón
transversal a PyPI, npm y RubyGems, no exclusivo de un ecosistema.

Técnica MITRE ATT&CK relacionada: T1195.001 (Compromise Software
Dependencies and Development Tools).
