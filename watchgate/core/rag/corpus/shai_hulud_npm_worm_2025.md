# Caso: gusano "Shai-Hulud" en npm (septiembre-noviembre 2025)

## Resumen

El 15 de septiembre de 2025 se detectó el primer gusano
**auto-propagante** conocido en el ecosistema npm. Partiendo de paquetes ya
comprometidos en el ataque previo a Nx ("s1ngularity"), el atacante
republicó versiones maliciosas de varios paquetes npm populares con un
script `postinstall` que, al ejecutarse durante `npm install`, robaba
credenciales del entorno de la víctima y usaba cualquier token de npm
encontrado para publicar automáticamente versiones maliciosas de **todos
los paquetes accesibles con ese token**, repitiendo el ciclo. Una segunda
oleada ("Shai-Hulud V2" / "The Second Coming"), detectada en noviembre de
2025, llegó a comprometer más de 700 paquetes y creó más de 27.000
repositorios públicos maliciosos en GitHub.

## Vector de introducción y mecánica del payload

- El payload vivía en un script `postinstall` del `package.json`, que se
  ejecuta automáticamente sin intervención humana en cuanto alguien (o un
  pipeline de CI) instala el paquete — no hace falta que nadie ejecute nada
  explícitamente.
- Para robar credenciales usaba **TruffleHog**, una herramienta legítima de
  escaneo de secretos, descargada y ejecutada contra el sistema de ficheros
  de la víctima — abuso de una herramienta de seguridad real con fines
  ofensivos, no malware "hecho a mano".
- Además de TruffleHog, recolectaba variables de entorno y credenciales de
  nube expuestas vía IMDS (metadata service de instancias cloud).
- Si encontraba un token de GitHub válido, ejecutaba dos scripts
  (`/tmp/processor.sh` y `/tmp/migrate-repos.sh`) que: creaban una rama
  `shai-hulud` y subían un workflow malicioso de GitHub Actions a **todos**
  los repositorios accesibles con ese token, y forzaban repositorios
  privados a visibilidad pública añadiendo el sufijo `-migration` al
  nombre — exfiltración y auto-propagación combinadas en el mismo paso.
- La exfiltración final de secretos se hacía a través del propio log del
  workflow de GitHub Actions (visible públicamente en un repo ahora
  público) y, en la primera oleada, también a un endpoint externo
  (`webhook[.]site`).
- **Propagación en cadena real**: si el token de npm robado tenía permisos
  de publicación sobre otros paquetes, el gusano publicaba versiones
  troyanizadas de esos paquetes también, sin intervención del atacante —
  cada nueva víctima se convertía automáticamente en vector para las
  siguientes.

## Patrón a vigilar

Script `postinstall`/`preinstall` nuevo o modificado que descarga binarios
externos o inspecciona variables de entorno/tokens; workflow de GitHub
Actions nuevo o alterado sin relación aparente con el resto del cambio.

Técnica MITRE ATT&CK relacionada: T1195.001 (Compromise Software
Dependencies and Development Tools), T1552 (Unsecured Credentials), T1567
(Exfiltration Over Web Service).

Fuentes: Wiz, Unit42 (Palo Alto Networks), CISA (alerta del 23/09/2025),
Microsoft Security Blog (guía sobre Shai-Hulud 2.0, 09/12/2025).
