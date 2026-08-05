# MITRE ATT&CK T1584 — Compromise Infrastructure

## Descripción

El adversario compromete infraestructura de un tercero (servidores,
dominios, servicios web/DNS) para usarla durante el ataque, en vez de
comprar o alquilar la suya propia. MITRE señala que esto permite que la
actividad del atacante se mezcle con tráfico que parece normal —contacto
con sitios de buena reputación o de confianza—, en vez de levantar sospecha
por apuntar a infraestructura nueva y desconocida.

## Casos de este corpus que son ejemplos directos de esta técnica

- `polyfill_io_cdn_compromise.md` — el dominio y servicio CDN cambiaron de
  propietario legalmente; el código servido desde una URL que cientos de
  miles de sitios ya referenciaban empezó a ser malicioso sin que ningún
  sitio afectado cambiara una línea de su propio código.
- `codecov_bash_uploader_compromise.md` — un script alojado en
  infraestructura de un proveedor de confianza (Codecov) fue modificado en
  origen; miles de pipelines de CI de terceros lo descargaban y ejecutaban
  de buena fe, sin ningún cambio en su propio repositorio.
- `pypi_telegram_c2_exfiltration_cluster.md` — uso de la API de bots de
  Telegram (dominio de reputación muy alta, `api.telegram.org`) como canal
  de exfiltración precisamente porque no levanta las mismas alarmas que un
  dominio desconocido.

## Por qué es relevante para WatchGate

- Es la técnica que conecta el hilo común de tres casos de ecosistemas
  distintos (CDN de JavaScript, herramienta de CI, API de mensajería): el
  atacante no necesita comprometer el proyecto objetivo en absoluto si
  puede comprometer algo en lo que el proyecto objetivo **ya confía por
  referencia externa** (una URL, un dominio, un script descargado).
- Refuerza la regla ya aplicada en `docker_typosquatted_base_images.md` y
  `polyfill_io_cdn_compromise.md`: cualquier referencia externa por
  nombre/URL sin fijar por contenido (hash, checksum, versión pinneada)
  hereda indefinidamente el riesgo de quien controle ese recurso en el
  futuro, no solo de quien lo controlaba cuando se escribió el diff que lo
  introdujo — y ese riesgo nunca aparece en un commit posterior, porque
  nada cambia en el propio repositorio.
