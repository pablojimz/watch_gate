# Caso: imágenes base de Docker Hub troyanizadas o con *typosquatting*

## Resumen

Patrón documentado repetidamente por investigadores de seguridad (Sysdig,
Kromtech Security, Aqua Security) desde 2018: imágenes públicas subidas a
Docker Hub que imitan el nombre de proyectos populares y oficiales (variantes
con guiones, sufijos o namespaces personales en vez de `library/`), o que
directamente eran versiones troyanizadas de imágenes legítimas, con un
minero de criptomonedas o una puerta trasera embebidos y activados vía
`ENTRYPOINT`/`CMD` en el arranque del contenedor. Varias de estas campañas
acumularon millones de descargas antes de ser detectadas y retiradas.

A diferencia de XZ Utils o `ctx`, aquí el contenido malicioso no vive en el
código fuente de un proyecto, sino en la propia imagen ya construida — lo
que la hace invisible a una revisión de código tradicional si nadie audita
el `Dockerfile` que decide de dónde viene esa imagen.

## Vector de introducción (relevante para un diff de PR)

Lo que sí es visible y revisable en un PR es el propio `Dockerfile`/
`docker-compose.yml`, y los cambios más habituales que introducen este riesgo
son:

- Cambiar la imagen base de una oficial y pinneada por digest
  (`FROM python:3.11@sha256:...`) a un namespace de usuario personal o un tag
  mutable sin pin (`FROM alguien/python-slim:latest`) — el contenido de ese
  tag puede cambiar después de que el PR se revise y apruebe, sin que quede
  reflejado en ningún diff posterior.
- Añadir un paso `RUN curl ... | sh` o `ADD http://... /` dentro del
  `Dockerfile` para traer algo en tiempo de build, en vez de declararlo como
  dependencia versionada — mismo patrón que el `curl | bash` en un
  `post_install` de PKGBUILD, solo que en la capa de build de la imagen.
- Un `ENTRYPOINT`/`CMD` que ejecuta un script adicional no presente en el
  repositorio (descargado en el propio `RUN`), en vez de arrancar
  directamente el proceso de la aplicación.

## Por qué es relevante para WatchGate

- El diff de un PR **sí** puede capturar el momento exacto en que se
  introduce el riesgo (el cambio de `FROM` o el `RUN curl | sh`), aunque el
  contenido malicioso final viva fuera del repositorio (en el registry de
  imágenes) — la capa estática debe tratar un `Dockerfile` igual que un
  script de build de cualquier otro ecosistema: llamadas de red y ejecución
  de código descargado son señales de riesgo, no solo en PKGBUILD o en
  workflows de CI.
- Un cambio de imagen base a un tag mutable y sin firmar/pinnear es análogo a
  "firmado con clave nunca vista" en la capa de reputación, pero aplicado a
  dependencias de infraestructura en vez de a un commit: se pierde la
  garantía de que lo que se revisó hoy es lo que se ejecutará mañana.
- Para la capa semántica: la pregunta relevante no es solo "¿qué hace este
  `RUN`?", sino "¿por qué esta imagen necesita construirse o arrancar
  descargando algo que no está versionado en el propio repositorio?".

Técnicas MITRE ATT&CK relacionadas: T1195.002 (Compromise Software Supply
Chain) y T1027 (Obfuscated Files or Information, el propio binario del
minero suele venir empaquetado/ofuscado dentro de la imagen).
