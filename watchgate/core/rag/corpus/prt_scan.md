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

## Por qué es relevante para WatchGate

- Es el caso de referencia para el vector "PR generado por IA adaptado al
  lenguaje del proyecto": el *contenido* del diff puede parecer idiomático y
  razonable a primera vista, por lo que la capa semántica debe fijarse en la
  **intención funcional** del cambio (¿por qué un workflow de CI necesita
  hacer una llamada de red con el valor de un secret?) y no solo en si el
  estilo del código "encaja".
- Refuerza la regla de forzado de capa semántica sobre cambios en
  `.github/workflows/*.yml` (ver `shortcircuit.py`), y es un ejemplo directo
  de por qué la capa estática debe marcar como sospechosa cualquier llamada
  de red dentro de ficheros de build/CI (`network-call-in-build-script`).
- La señal de reputación es también relevante aquí: cuentas con poco o ningún
  historial de contribución al repositorio concreto, abriendo PRs no
  solicitados.

Técnica MITRE ATT&CK relacionada: T1195 (Supply Chain Compromise) sobre la
cadena de CI/CD, con exfiltración de credenciales como objetivo final.
