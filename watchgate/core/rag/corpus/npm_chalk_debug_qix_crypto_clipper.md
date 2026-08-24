# Caso: chalk/debug — el mayor compromiso de npm hasta la fecha (septiembre 2025)

## Resumen

El 8 de septiembre de 2025, el mantenedor de npm conocido como "Qix" —autor
de paquetes fundacionales del ecosistema JavaScript como `chalk`, `debug`,
`ansi-styles`, `strip-ansi`, `color-convert` y otros 13 más, con más de
**2.000 millones de descargas semanales combinadas**— fue víctima de un
phishing dirigido. El atacante publicó versiones menores maliciosas de los
18 paquetes comprometidos, insertando un *crypto-clipper* (malware que
intercepta y sustituye direcciones de criptomonedas en tiempo real) en
cada uno. Dado que estos paquetes son dependencias transitivas de una parte
enorme del ecosistema npm, el radio de explosión potencial superaba los 20
millones de paquetes — en torno al 34% de todo npm. Las versiones
maliciosas estuvieron publicadas unas 2,5 horas antes de que npm
interviniera; una herramienta de monitorización (Aikido) detectó la
anomalía en apenas 5 minutos. Amazon atribuyó posteriormente el ataque al
grupo norcoreano Sapphire Sleet.

## Vector de introducción

- El atacante envió un correo de phishing suplantando al soporte de npm,
  desde un dominio parecido pero falso (`npmjs.help`), amenazando con el
  bloqueo de la cuenta si no se actualizaban los ajustes de 2FA. El
  mantenedor introdujo usuario, contraseña y un código TOTP válido en el
  momento — suficiente para que el atacante tomara control total de la
  cuenta de publicación de inmediato.
- El payload es un script que **solo se ejecuta en navegador** (no en
  Node.js del lado servidor), centrado en interceptar transacciones cripto
  y llamadas a APIs Web3.
- Mecanismo técnico: el código sobrescribe `fetch`, `XMLHttpRequest` y las
  APIs de wallet inyectadas en la página (`window.ethereum` para
  MetaMask/EVM, equivalentes para Solana) para inspeccionar las respuestas
  en busca de direcciones de blockchain (reconoce formatos de Ethereum,
  Bitcoin, Solana, Tron, Litecoin y Bitcoin Cash) y sustituirlas por
  direcciones del atacante **visualmente similares** (usando un algoritmo
  de distancia de Levenshtein para elegir la dirección falsa más parecida
  a la real, dificultando que la víctima note el cambio a simple vista).
- Comportamiento sigiloso deliberado: si detecta una wallet activa, evita
  cambios obvios en la interfaz visible y mantiene los *hooks* silenciosos
  operando en segundo plano, interceptando y alterando transacciones reales
  sin ningún indicio visual de que algo ha cambiado.

## Patrón a vigilar

Paquete de utilidad genérico (sin relación aparente con criptomonedas o
Web3) que en una actualización de versión menor empieza a sobrescribir
`fetch`/`XMLHttpRequest` globales o a interactuar con `window.ethereum`
u objetos de wallet — funcionalidad completamente ajena al propósito
declarado del paquete (formateo de texto de terminal, en el caso de
`chalk`; logging, en el caso de `debug`).

Técnica MITRE ATT&CK relacionada: T1078 (Valid Accounts — phishing a un
mantenedor con acceso de publicación), T1195.001 (Compromise Software
Dependencies and Development Tools).
