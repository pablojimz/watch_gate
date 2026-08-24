# Caso: colors.js + faker.js — autosabotaje del mantenedor (GHSA-gh88-3pxp-6fm8, GHSA-5w9c-rv96-fr7g)

## Resumen

En enero de 2022, el mantenedor de `colors` (paquete npm de formateo de
texto en terminal, con cientos de millones de descargas mensuales a través
de dependencias transitivas) publicó una versión con un bucle infinito
deliberado (`for (let i = 666; i < Infinity; i++)`) que rompía cualquier
proyecto que lo usara — protesta pública contra grandes empresas que usan
paquetes open source gratuitos sin compensar a sus mantenedores. Dos meses
después, el mismo mantenedor hizo lo mismo con `faker.js` (generador de
datos de prueba), eliminando por completo el código funcional del paquete.

## Vector de introducción

- Igual que `node_ipc_protestware.md`: el propio mantenedor legítimo, con
  acceso real y de largo plazo, decidió sabotear su propio paquete — no
  hay secuestro de cuenta que detectar.
- El "666" en el bucle infinito es una firma deliberada, casi una
  declaración pública del propio autor de que el sabotaje era intencional
  — no se disimuló como un bug accidental.
- Según el aviso de GitHub, otros mantenedores del paquete perdieron el
  control sobre él durante el incidente, lo que sugiere que el autor
  original revocó intencionadamente el acceso de terceros para impedir que
  se revirtiera el cambio.

## Patrón a vigilar

Bucle infinito o lógica destructiva sin relación con el cambio funcional
descrito en el commit, introducida por el propio mantenedor habitual
(denegación de servicio deliberada, no exfiltración/backdoor).
