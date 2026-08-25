# Caso: GlassWorm — gusano de extensiones VS Code con Unicode invisible (octubre 2025)

## Resumen

En octubre de 2025, investigadores de Koi Security descubrieron GlassWorm,
el primer gusano auto-propagante conocido dirigido a extensiones de VS
Code en el marketplace OpenVSX. Siete extensiones fueron comprometidas el
17 de octubre de 2025, con unas 35.800 descargas acumuladas; dos días
después, diez extensiones seguían distribuyendo malware activamente. El
malware roba credenciales, se auto-replica usando esas mismas credenciales
robadas para comprometer más extensiones, y usa la blockchain de Solana
como infraestructura de mando y control (C2). MITRE lo cataloga como
S9010, dentro de la sub-técnica T1195.001.

## Vector de introducción

- **Ofuscación mediante Unicode invisible**: en vez de recurrir a
  ofuscación clásica (base64, minificado, empaquetado), los atacantes
  usaron caracteres Unicode invisibles — concretamente *variation
  selectors* y caracteres del área de uso privado (Private Use Area, PUA).
  El código malicioso literalmente **desaparece de la vista en el editor**
  durante una revisión: no es que sea difícil de leer, es que no se
  renderiza en absoluto. Un revisor humano mirando el fichero ve código
  aparentemente normal y completo.
- **Robo de credenciales**: recolecta credenciales de NPM, GitHub y Git, y
  ataca 49 extensiones distintas de carteras de criptomonedas.
- **Auto-propagación**: las credenciales robadas se usan automáticamente
  para comprometer paquetes y extensiones adicionales del desarrollador
  víctima, creando un ciclo de auto-replicación de crecimiento exponencial
  a través del ecosistema — el mismo mecanismo conceptual que Shai-Hulud
  en npm, pero sobre el marketplace de extensiones del editor.
- **Persistencia y acceso remoto**: despliega servidores proxy SOCKS
  (convirtiendo la máquina del desarrollador en infraestructura criminal) e
  instala servidores VNC ocultos para acceso remoto completo.
- **C2 sobre blockchain**: usar la blockchain de Solana como canal de mando
  y control hace que la infraestructura sea muy difícil de derribar — no
  hay un dominio o servidor que un registrador o proveedor pueda retirar.
- En oleadas posteriores el malware evolucionó a implantes escritos en Rust
  empaquetados dentro de las propias extensiones.

## Patrón a vigilar

Presencia de caracteres Unicode invisibles —*variation selectors*
(`U+FE00`-`U+FE0F`) y área de uso privado (`U+E000`-`U+F8FF`)— en ficheros
de código fuente. Complementa el rango de control bidireccional ya
documentado en `trojan_source_unicode_bidi.md`: en aquel caso el orden de
renderizado engaña al revisor, aquí el código directamente no se muestra.
En ambos, la detección debe hacerse sobre los *bytes reales* del fichero,
nunca sobre lo que se ve renderizado.

Técnica MITRE ATT&CK relacionada: T1195.001 (Compromise Software
Dependencies and Development Tools — GlassWorm figura como S9010), T1027
(Obfuscated Files or Information), en particular T1027.018 (Invisible
Unicode), T1552 (Unsecured Credentials), T1102 (Web Service — blockchain
de Solana como canal de C2).
