# MITRE ATT&CK T1584 — Compromise Infrastructure

**Táctica:** Resource Development. **Plataformas:** PRE (pre-compromiso).
**Versión:** 1.6 (última modificación: 24 de octubre de 2025).

## Descripción

El adversario compromete infraestructura de terceros — "servidores físicos
o en la nube, dominios, dispositivos de red y servicios web/DNS de
terceros" — para usarla durante sus operaciones, en vez de adquirirla
legítimamente. En lugar de comprar o alquilar infraestructura propia, el
atacante reutiliza activos comprometidos para preparar y ejecutar
operaciones mientras mezcla su actividad con patrones de tráfico
legítimos. Esta técnica habilita actividad maliciosa de seguimiento, y
puede incluso implicar comprometer infraestructura perteneciente a otros
actores de amenaza rivales.

## Sub-técnicas

- **T1584.001** — Domains
- **T1584.002** — DNS Server
- **T1584.003** — Virtual Private Server
- **T1584.004** — Server
- **T1584.005** — Botnet
- **T1584.006** — Web Services
- **T1584.007** — Serverless
- **T1584.008** — Network Devices

## Ejemplos de procedimiento

- **APT28, Campaña "Nearest Neighbor" (C0051)** — "Comprometió
  infraestructura de terceros en proximidad física a objetivos de interés
  para actividad de seguimiento", aprovechando redes Wi-Fi cercanas para
  acceso encubierto.
- **Intrusiones a infraestructura crítica india (C0043)** — Esta campaña
  "incluyó el uso de infraestructura comprometida, como dispositivos DVR y
  cámaras IP, para mando y control" en operaciones ShadowPad.

## Mitigaciones (MITRE)

**M1056 — Pre-compromise**: "Esta técnica no se puede mitigar fácilmente
con controles preventivos, ya que se basa en comportamientos realizados
fuera del alcance de las defensas y controles empresariales."

## Estrategia de detección (MITRE)

**DET0885** — Vigilar patrones identificables en la infraestructura
aprovisionada por el atacante (servicios escuchando, certificados en uso,
características de negociación SSL/TLS, u otros artefactos de respuesta
asociados a software de C2). También: seguimiento de cambios anómalos de
registro de dominio y monitorización de datos de resolución DNS en busca
de indicadores de compromiso.

## Casos de este corpus que son ejemplos directos de esta técnica

- `polyfill_io_cdn_compromise.md` — el dominio y servicio CDN cambiaron de
  propietario legalmente; el código servido desde una URL que cientos de
  miles de sitios ya referenciaban empezó a ser malicioso sin que ningún
  sitio afectado cambiara una línea de su propio código.
- `codecov_bash_uploader_compromise.md` — un script alojado en
  infraestructura de un proveedor de confianza (Codecov) fue modificado en
  origen; miles de pipelines de CI lo descargaban y ejecutaban de buena fe.
- `pypi_telegram_c2_exfiltration_cluster.md` — uso de la API de bots de
  Telegram (dominio de reputación muy alta) como canal de exfiltración.

## Nota WatchGate

El atacante no necesita comprometer el proyecto objetivo si puede
comprometer algo en lo que ese proyecto **ya confía por referencia
externa** (una URL, un dominio, un script descargado). Cualquier
referencia externa sin fijar por contenido (hash, checksum, versión
pinneada) hereda indefinidamente el riesgo de quien controle ese recurso
en el futuro — riesgo que nunca aparece en un commit posterior, porque
nada cambia en el propio repositorio.
