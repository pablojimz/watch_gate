# Caso: node-ipc — "protestware" (GHSA-8gr3-2gjw-jj7g)

## Resumen

En marzo de 2022, el mantenedor legítimo de `node-ipc` (paquete npm con
millones de descargas semanales, dependencia transitiva de herramientas
muy usadas como Vue CLI) añadió una dependencia nueva que, en máquinas con
dirección IP geolocalizada en Rusia o Bielorrusia, escribía ficheros
arbitrarios en el disco del usuario — en protesta por la invasión rusa de
Ucrania. GitHub lo clasificó oficialmente como "hidden functionality"
(funcionalidad oculta) introducida deliberadamente por el propio
mantenedor.

## Vector de introducción

- A diferencia de la mayoría de casos de este corpus, aquí **no hubo
  ningún secuestro de cuenta ni ingeniería social**: fue el propio
  mantenedor legítimo, con acceso de publicación real y de largo plazo,
  quien introdujo el comportamiento malicioso a propósito.
- El payload vivía en una dependencia nueva y separada del paquete
  principal, activada condicionalmente según la geolocalización de la IP
  del usuario — el comportamiento normal seguía funcionando igual para la
  inmensa mayoría de instalaciones, dificultando la detección temprana.
- Se conoce como "protestware": código malicioso motivado por una postura
  política o social del propio autor, no por beneficio económico directo.

## Patrón a vigilar

Lógica condicional basada en geolocalización de IP, sin relación con la
funcionalidad del paquete, introducida por el propio mantenedor habitual.
