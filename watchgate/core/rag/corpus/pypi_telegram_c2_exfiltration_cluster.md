# Patrón: Telegram como canal de exfiltración/C2 en paquetes PyPI maliciosos

## Resumen

A diferencia de los demás casos de este corpus (incidentes individuales,
documentados en profundidad), esto es un **patrón recurrente** observado en
varios paquetes maliciosos de PyPI distintos, vía los avisos automáticos de
`OSV.dev` (aviso corto de detección, no una investigación completa como la
de `ctx`, pero real y verificable). Seis paquetes confirmados como
maliciosos, en dos oleadas distintas, comparten el mismo canal de
exfiltración: la API de bots de Telegram, en vez de un servidor propio.

| Paquete | Ecosistema | Publicado | Comportamiento |
|---|---|---|---|
| `costrar`, `nasrtox`, `tensorfioi` | PyPI | jun. 2024 | Se comunican con un host desconocido vía un canal de Telegram |
| `requestn` | PyPI | jun. 2024 | Extrae ficheros del sistema local y los envía por Telegram |
| `ilovenyxx`, `ilovenyxxbait` | PyPI | ene. 2025 | Infostealer: exfiltra ficheros sensibles y credenciales de bases de datos de navegadores vía Telegram |

## Por qué Telegram como canal

- La API de bots de Telegram (`api.telegram.org`) es HTTPS estándar hacia un
  dominio legítimo y de reputación alta — no levanta las mismas alarmas de
  red que una IP o dominio recién registrado y desconocido.
- No requiere que el atacante mantenga su propia infraestructura de
  servidor (a diferencia del caso `ctx`, que usaba una app de Heroku
  propia): un bot de Telegram gratuito es suficiente como receptor,
  reduciendo el coste y la superficie de detección del atacante.
- El patrón se repite con nombres de paquete genéricos o que imitan
  ligeramente a paquetes populares (`requestn` vs. `requests`), sugiriendo
  automatización o un mismo actor probando variantes.

## Por qué es relevante para WatchGate

- La capa semántica debe tratar cualquier llamada de red hacia
  `api.telegram.org` (o APIs de mensajería/bot similares) desde código que
  no sea explícitamente una integración de mensajería como una señal de
  igual peso que una llamada a un dominio desconocido — el destino "parece"
  legítimo, pero el contexto (un paquete de utilidad genérico enviando
  datos a un bot de Telegram) no lo es.
- Refuerza el mismo patrón ya documentado en `pypi_ctx_env_exfiltration.md`
  (recolección de datos sensibles + exfiltración por red desde código de
  uso aparentemente normal), con un canal de transporte distinto.
- Ejemplo de por qué la consulta automática a OSV (`gather_dependency_findings`)
  importa: estos paquetes están documentados y son detectables por nombre
  exacto antes de que el LLM tenga que razonar sobre el código en sí.
