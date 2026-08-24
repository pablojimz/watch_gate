# Caso: @solana/web3.js (npm, CVE-2024-54134) — robo de claves privadas vía phishing

## Resumen

El 3 de diciembre de 2024, un miembro del equipo con permisos de
publicación sobre el paquete npm `@solana/web3.js` (más de 450.000
descargas semanales, librería estándar para interactuar con la blockchain
de Solana) fue víctima de un ataque de *spear-phishing* dirigido. El
atacante publicó dos versiones maliciosas (`1.95.6` y `1.95.7`) que
capturaban y exfiltraban las claves privadas de cualquier aplicación que
las usara para firmar transacciones. Se detectaron y retiraron en horas,
pero aun así se robaron más de 190.000 $ en criptomoneda de aplicaciones
que instalaron esas versiones durante la ventana de unas 5 horas en que
estuvieron publicadas.

## Vector de introducción

- El vector inicial no fue técnico: un correo de invitación (aparentando
  venir de otro miembro del propio equipo) llevaba a una réplica falsa de
  la web de npm, donde la víctima introdujo usuario, contraseña y el
  código de doble factor — el atacante los capturó en tiempo real y los
  reutilizó de inmediato para publicar.
- El código malicioso añadía una función (`addToQueue`) que interceptaba
  las claves privadas usadas para firmar transacciones y las enviaba a una
  dirección de wallet controlada por el atacante — sin cambiar
  visiblemente el comportamiento normal de la librería, que seguía
  funcionando con normalidad desde el punto de vista del desarrollador.
- Alcance limitado por ventana temporal, no por diseño: solo las
  instalaciones/actualizaciones realizadas durante esas ~5 horas exactas
  quedaron expuestas — cualquier build anterior o posterior a esa ventana
  usaba una versión limpia, lo que dificultó dimensionar el impacto real
  hasta pasado un tiempo.

## Por qué es relevante para WatchGate

- Caso de referencia de que el compromiso puede llegar por una vía
  totalmente ajena al propio código del repositorio auditado: nada en el
  diff de un PR normal revela un maintainer de una dependencia
  phisheado — el riesgo entra en el próximo `npm install`/actualización de
  versión, no en un cambio de código local.
- Relevante para la capa de dependencias: un `package.json`/lockfile que
  actualiza `@solana/web3.js` (o cualquier paquete) a una versión recién
  publicada, sin ventana de confianza tras su publicación, es
  estructuralmente el mismo patrón de riesgo — versiones "recién salidas
  del horno" tienen menos tiempo acumulado de escrutinio de la comunidad.
- Técnica MITRE ATT&CK relacionada: T1078 (Valid Accounts — credenciales
  legítimas de un mantenedor real, no explotación de una vulnerabilidad),
  T1195.001 (Compromise Software Dependencies and Development Tools).
