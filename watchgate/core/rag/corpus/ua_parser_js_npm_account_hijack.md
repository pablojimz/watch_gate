# Caso: ua-parser-js (npm) — secuestro de cuenta de mantenedor (octubre 2021)

## Resumen

El 22 de octubre de 2021, la cuenta de npm del mantenedor de
`ua-parser-js` (librería para identificar navegador/dispositivo a partir
del User-Agent, usada por Facebook, Amazon, Microsoft y millones de
proyectos como dependencia transitiva) fue secuestrada. El atacante
publicó tres versiones maliciosas — 0.7.29, 0.8.0 y 1.0.0, una por cada
línea de versiones activa, para maximizar el alcance en instalaciones con
rangos `^`/`~` — que descargaban e instalaban un minero de criptomonedas
y un ladrón de credenciales. El incidente motivó una alerta oficial de
CISA. Las versiones limpias 0.7.30, 0.8.1 y 1.0.1 se publicaron el mismo
día.

## Vector de introducción

- El compromiso fue de la CUENTA del mantenedor, no del repositorio: el
  código en GitHub permaneció limpio mientras npm servía versiones
  envenenadas. Cualquier revisión que mirase solo el repositorio oficial
  no veía nada — la divergencia entre el tarball publicado en el registro
  y el código fuente del repo es en sí misma la señal.
- El payload se activaba vía script `preinstall` en `package.json`, que
  npm ejecuta automáticamente al instalar: detectaba el sistema operativo
  y lanzaba `preinstall.bat` (Windows) o un script shell (Linux), que
  descargaba binarios externos — un minero (variante de XMRig) y, en
  Windows, una DLL ladrona de credenciales (identificada como DanaBot).
- Los binarios se descargaban de IPs externas en tiempo de instalación:
  el paquete en el registro apenas contenía el dropper, dificultando el
  análisis estático del tarball.
- Publicar las tres líneas de versión a la vez (0.7.x, 0.8.x, 1.0.x) es
  una decisión deliberada del atacante para cubrir tanto proyectos
  anclados a versiones viejas como a las nuevas.

## Patrón a vigilar

Aparición de scripts de ciclo de vida (`preinstall`, `install`,
`postinstall`) en un `package.json` que antes no los tenía, sobre todo si
invocan ficheros específicos de plataforma (`.bat`, `.sh`) o descargan
binarios de URLs/IPs externas en tiempo de instalación. Una versión nueva
de una librería utilitaria pura (parsear un User-Agent no necesita
ejecutar nada al instalarse) que añade estos hooks es una señal máxima.

Técnica MITRE ATT&CK relacionada: T1195.001 (Compromise Software
Dependencies and Development Tools), T1078 (Valid Accounts — cuenta de
mantenedor secuestrada), T1496 (Resource Hijacking — criptominado).
