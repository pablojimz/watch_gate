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

## Por qué es relevante para WatchGate

- Categoría de riesgo distinta a los demás casos del corpus: no es
  exfiltración, backdoor ni escalada de privilegios — es **denegación de
  servicio deliberada**, y aun así el mismo principio aplica: el contenido
  del cambio importa más que quién lo firma, incluso si quien lo firma es
  el propio mantenedor de siempre.
- Útil para calibrar la categoría `ninguna` vs. una categoría de riesgo:
  un bucle `for (i = 0; i < Infinity; i++)` sin ninguna condición de
  salida, introducido sin relación con ningún cambio funcional descrito en
  el commit, es una señal de sabotaje aunque no robe ni ejecute nada
  externo.
- Recordatorio de que "reputación heredada" (mismo autor de siempre, mismo
  paquete de siempre) es exactamente la señal que un atacante —o un
  mantenedor descontento— puede explotar mejor, porque es la que menos
  escrutinio recibe por defecto.
