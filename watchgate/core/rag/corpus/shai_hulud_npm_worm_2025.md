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

## Por qué es relevante para WatchGate

- Es la referencia más reciente y mejor documentada de un patrón que
  probablemente seguirá repitiéndose: **abuso de scripts de instalación de
  gestores de paquetes (`postinstall`, `preinstall`) como vector de
  ejecución automática**, sin que la víctima haga nada más que instalar
  una dependencia — igual que en `event-stream`, pero con auto-replicación
  añadida.
- El hecho de que use una herramienta de seguridad legítima (TruffleHog)
  como parte del payload es un recordatorio de que "la herramienta es
  conocida y confiable" no dice nada sobre si su presencia en un contexto
  concreto (descargada dinámicamente dentro de un script de instalación)
  es legítima.
- Un cambio que añade o modifica un script `postinstall`/`preinstall` en
  `package.json`, especialmente si descarga binarios externos o inspecciona
  variables de entorno y tokens, merece el mismo nivel de sospecha que
  código ejecutable añadido directamente al proyecto — el punto de entrada
  no es menos peligroso por ser "solo configuración de npm".
- Modificar un workflow de GitHub Actions (crear uno nuevo o alterar uno
  existente) como parte de un cambio que no tiene relación aparente con
  CI/CD es en sí misma una señal fuerte, incluso sin ver el contenido
  exacto del workflow — es exactamente el mecanismo de propagación de este
  caso.
- Técnica MITRE ATT&CK relacionada: T1195.001 (Compromise Software
  Dependencies and Development Tools), T1552 (Unsecured Credentials),
  T1567 (Exfiltration Over Web Service).

Fuentes: Wiz, Unit42 (Palo Alto Networks), CISA (alerta del 23/09/2025),
Microsoft Security Blog (guía sobre Shai-Hulud 2.0, 09/12/2025).
