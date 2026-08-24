# Caso: campaña "prt-scan" contra GitHub Actions

## Resumen

Campaña identificada por investigadores de seguridad (Wiz Research) en la que
se usó un conjunto reducido de cuentas de GitHub controladas por el atacante
para abrir *pull requests* automatizados, generados con ayuda de modelos de
lenguaje, contra numerosos repositorios que usan GitHub Actions. El objetivo
era introducir modificaciones en *workflows* de CI/CD para exfiltrar secretos
(tokens, credenciales de despliegue) definidos como `secrets.*` del repositorio.

## Vector de introducción

- Los PRs se generaban de forma semi-automática y el *payload* se adaptaba al
  lenguaje/framework del proyecto objetivo (Node, Python, Go...), de forma que
  el cambio "encajaba" estilísticamente con el resto del código del repo —
  precisamente el tipo de mimetismo que un LLM puede producir a escala y que
  dificulta la detección basada solo en heurísticas de estilo.
- El vector concreto solía ser una modificación a un fichero de workflow
  (`.github/workflows/*.yml`) añadiendo un paso que exporta variables de
  entorno con secretos hacia una llamada de red externa, o registra su valor
  en un log accesible públicamente en `Actions`.
- Un pequeño número de cuentas (seis, según el informe de Wiz) concentraba un
  volumen de PRs desproporcionadamente alto contra repositorios no
  relacionados entre sí, sin interacción previa ni historial de
  contribuciones genuinas en esos proyectos.

## Patrón a vigilar

PR no solicitado, de una cuenta sin historial de contribución, que
modifica `.github/workflows/*.yml` con una llamada de red usando el valor
de un secret.

Técnica MITRE ATT&CK relacionada: T1195 (Supply Chain Compromise) sobre la
cadena de CI/CD.
