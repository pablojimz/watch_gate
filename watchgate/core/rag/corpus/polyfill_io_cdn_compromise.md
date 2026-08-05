# Caso: polyfill.io — compromiso de un CDN de JavaScript ampliamente referenciado

## Resumen

`polyfill.io` era un servicio CDN muy popular que servía polyfills de
JavaScript (código de compatibilidad con navegadores antiguos) a más de
100.000 sitios web, referenciado directamente en el HTML de esos sitios
mediante una etiqueta `<script src="https://cdn.polyfill.io/...">`. A
mediados de 2024 se hizo público que el dominio y el servicio habían sido
adquiridos por una entidad distinta a los mantenedores originales, y que el
código servido desde ese dominio empezó a incluir redirecciones y
comportamiento malicioso inyectado dinámicamente en los sitios que lo
referenciaban. Ante la repercusión, Cloudflare y Fastly montaron réplicas
alternativas del servicio original para que los sitios afectados pudieran
migrar sin tener que auditar ni reescribir su propio código.

## Vector de introducción

- No hubo ningún cambio de código en los sitios afectados: la etiqueta
  `<script src="https://cdn.polyfill.io/...">` llevaba semanas o meses sin
  tocarse en el repositorio de cada sitio, pero el contenido servido desde
  esa URL cambió sin que ningún commit lo reflejara.
- Es el mismo patrón ya documentado en `docker_typosquatted_base_images.md`
  para imágenes de Docker con tags mutables, pero aplicado a una
  referencia CDN en HTML/JavaScript: **referenciar un recurso externo por
  URL en vez de vendorizarlo o pinnearlo por versión/hash** traslada la
  confianza a quien controle ese dominio en el futuro, no solo a quien lo
  controlaba cuando se añadió la referencia.
- El cambio de propietario del dominio fue completamente legal y visible
  públicamente (transferencia de dominio), pero el cambio de intención del
  nuevo propietario no lo fue hasta que empezó a explotarse.

## Por qué es relevante para WatchGate

- Un diff que añade una referencia a un script de terceros por URL
  (`<script src="https://...">`, `@import url(...)`, o equivalentes en
  otros lenguajes) sin pinnear versión/hash es una señal de riesgo
  estructural por sí sola, con independencia de que el dominio referenciado
  parezca de confianza en el momento del PR — el propio caso XZ Utils y
  este demuestran que "de confianza hoy" no implica "de confianza mañana".
- Mismo principio ya aplicado a imágenes base de Docker
  (`docker_typosquatted_base_images.md`) y a los patrones de dependencias
  (`dependency_confusion.md`): cualquier referencia externa sin fijar por
  contenido (hash/checksum), solo por nombre o URL, es una promesa de
  confianza que puede romperse sin que quede registrado en ningún diff.

Técnica MITRE ATT&CK relacionada: T1195.002 (Compromise Software Supply
Chain).
