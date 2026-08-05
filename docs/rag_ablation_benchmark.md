# Comparativa con/sin RAG en la capa semántica

Este documento registra una pregunta concreta que nos hicimos: **¿el RAG
aporta algo de verdad, o Gemini ya sabría detectar esto solo?** En vez de
especular, se montó un pequeño banco de pruebas reutilizable para comparar
el mismo diff con y sin contexto RAG, contra la API real.

## Metodología

1. Construir un caso con `scripts/rag_ablation_cases.py --build <caso> --out <dir>`
   (genera un repo git desechable con dos commits: base y head).
2. Correr `scripts/smoke_test_linea2.py` **dos veces** sobre el mismo diff:
   una normal, otra con `--no-rag` (apunta a un índice vacío, así
   `retrieve_relevant_context` devuelve `[]` — mismo mecanismo que el caso
   "índice no existe" ya cubierto en `test_rag.py`).
3. Ambas ejecuciones quedan en `.watchgate/semantic_layer_log.jsonl`
   (gitignored) con la etiqueta puesta en `--label`, para poder comparar
   `risk_score`/`category`/`justification` sin repetir la llamada.

```
poetry run python scripts/rag_ablation_cases.py --build <caso> --out /tmp/caso1
# imprime los comandos exactos a copiar (con y sin --no-rag)
```

No usar `WATCHGATE_VT_API_KEY` durante estas comparaciones si se quiere
aislar el efecto del RAG del de la tool de VirusTotal.

## Casos disponibles (`scripts/rag_ablation_cases.py`)

| Caso | Qué prueba | Corpus RAG relacionado |
|---|---|---|
| `trojan-source` | Caracteres Unicode bidireccionales reales insertados en un comentario | `trojan_source_unicode_bidi.md` |
| `base64-exec` | Payload de reverse shell codificado en base64 y ejecutado con `exec()` | ninguno específico (patrón genérico de ofuscación) |
| `benign-plugin-loader` | Carga dinámica de plugins con `importlib`/`pkgutil` -- caso de **calibración**, no debería marcarse como malicioso | ninguno específico |
| `dependency-confusion` | Nueva dependencia con nombre de convención interna y versión inflada | `dependency_confusion.md` |
| `docker-base-image-swap` | Cambio de imagen base pinneada a un tag mutable + `RUN curl \| sh` | `docker_typosquatted_base_images.md` |
| `new-file-minimal-wiring` | Payload repartido entre un fichero nuevo y una línea de enganche en uno existente | `attck_t1027_obfuscated_files.md` |
| `github-actions-secret-leak` | Workflow de CI modificado para exfiltrar `secrets.*` vía un `curl` disfrazado de "debug step" | `prt_scan.md` |
| `telegram-c2-exfiltration` | Busca ficheros `.env`/credenciales de AWS locales y los sube a un bot de Telegram | `pypi_telegram_c2_exfiltration_cluster.md` |
| `docker-entrypoint-hijack` | `ENTRYPOINT` reescrito para descargar y ejecutar un script antes de arrancar la app real | `docker_typosquatted_base_images.md` (variante: hijack de entrypoint, no de imagen base) |
| `typosquat-popular-package` | Nueva dependencia `sympy-dev` (imita al paquete real `sympy`) | `dependency_confusion.md` (caso real `MAL-2026-450`) |
| `benign-curl-checksum-verified` | Calibración: usa `curl` (señal habitual de sospecha) pero de forma legítima -- descarga una release pinneada por versión y verifica su checksum antes de usarla | ninguno específico -- pensado para no disparar solo por ver `curl` |

## Resultados registrados

Solo se han ejecutado de verdad los dos primeros (contra Gemini real,
`gemini-2.5-flash`) -- el resto están listos para correr pero no se han
lanzado aún, para no gastar más llamadas de las necesarias.

### `trojan-source`

| | Con RAG | Sin RAG |
|---|---|---|
| `risk_score` | 98 | 45 |
| `category` | `escalada_privilegios` | `ofuscacion` |
| `confidence` | alta | alta |
| justificación | Identifica los codepoints exactos (`U+202E`, `U+2066`/`U+2069`), nombra la técnica y el CVE (Trojan Source, CVE-2021-42574), y describe la lógica de escalada oculta. | También identifica los mismos codepoints (no hace falta RAG para eso), pero razona que en Python el `#` comenta el resto de la línea, así que en este caso concreto el payload **no llega a ejecutarse** -- ofuscación sospechosa, no un ataque funcional confirmado. |

**Lectura:** en este caso concreto, la respuesta *sin* RAG es técnicamente
más rigurosa -- el caso de prueba metía el payload dentro del propio
comentario, así que nunca se ejecuta de verdad en Python. Con RAG, el
modelo reconoció la etiqueta de la técnica (nombre + CVE) y puntuó por ahí,
sin verificar con el mismo cuidado si el truco surtía efecto en este diff
en concreto. No invalida el RAG -- sí muestra que puede empujar hacia un
veredicto más severo basado en el *nombre* de un patrón conocido, en vez de
en el análisis línea a línea.

### `benign-plugin-loader`

| | Con RAG | Sin RAG |
|---|---|---|
| `risk_score` | 10 | 80 |
| `category` | `ninguna` (correcto) | `backdoor` (falso positivo) |
| confidence | alta | alta |
| justificación | Reconoce un patrón de diseño legítimo y común (carga dinámica de plugins). | "Permite la inyección y ejecución de código arbitrario si un atacante puede escribir en esa carpeta" -- técnicamente cierto de casi cualquier mecanismo de import dinámico, pero no es una señal real sin más contexto. |

**Lectura:** aquí el RAG mejora claramente la calibración. Sin él, el
modelo trata cualquier `importlib.import_module` dinámico como sospechoso
por defecto; con el contexto RAG (que incluye ejemplos de qué SÍ es un
patrón malicioso real: llamadas a dominios externos, exfiltración,
payloads codificados...) distingue mejor "código dinámico dentro de la
estructura propia del proyecto" de "código que trae algo de fuera".

## Conclusión provisional

El RAG **no es gratis ni neutro**: mejora la calibración frente a falsos
positivos en código técnico-pero-benigno, pero puede sesgar el veredicto
hacia la severidad asociada al *nombre* de una técnica conocida en vez de
verificar su efecto real en el diff concreto. Con solo 2 casos no se puede
generalizar -- de ahí este documento y el banco de casos reutilizable: para
ampliar la muestra sin tener que reconstruir cada caso a mano.

Pendiente: correr los 9 casos restantes (con y sin RAG) y, si el patrón de
"severidad inflada por el nombre de la técnica" se repite, considerar
añadir al prompt una instrucción explícita de verificar el efecto real
antes de puntuar por la etiqueta de un patrón conocido.

Los 5 casos nuevos (`github-actions-secret-leak`, `telegram-c2-exfiltration`,
`docker-entrypoint-hijack`, `typosquat-popular-package`,
`benign-curl-checksum-verified`) están construidos y verificados
localmente (el diff generado se ha revisado a mano), pero no se han
ejecutado todavía contra ningún LLM real -- pendientes de correr cuando se
decida ampliar la comparación.

## Actualización: colecciones separadas + corpus ampliado

A raíz de este hallazgo (RAG mejora la calibración pero puede inflar la
severidad por el nombre de una técnica reconocida), se rediseñó el RAG:

- `feedback_cases` es ahora una colección de ChromaDB separada de
  `attack_patterns`, con hueco garantizado en la recuperación
  (`retriever.py`, `feedback_k=1` por defecto) -- un caso confirmado del
  propio historial de revisión no compite por hueco contra el corpus
  público, que puede crecer mucho más que antes.
- El corpus público pasó de 12 a 20 documentos (8 casos reales nuevos,
  verificados contra OSV.dev antes de escribirlos).

Esto no cambia la conclusión de este documento (sigue siendo cierto que el
RAG puede sesgar el veredicto hacia la etiqueta de una técnica conocida),
pero sí cambia el contexto: con un corpus más grande, la probabilidad de
que el modelo reconozca *alguna* técnica por nombre es mayor, no menor --
la instrucción explícita de "verificar el efecto real antes de puntuar por
la etiqueta" (todavía no implementada) es ahora más relevante, no menos.

## Actualización: la instrucción de verificación, implementada y probada

Se implementaron dos capas de mitigación, probadas por separado contra
Gemini real con el mismo caso (`trojan-source`, con RAG activado):

1. **Recordatorio genérico en el prompt** (`_VERIFICATION_REMINDER` en
   `prompting.py`, siempre presente): pedir al modelo que verifique el
   efecto real antes de puntuar por el nombre de una técnica reconocida.
   **Resultado: sin cambio.** `risk_score` siguió en 98,
   `escalada_privilegios`, misma justificación errónea que antes.
2. **Comprobación específica en el propio documento del corpus**
   (`trojan_source_unicode_bidi.md`): en vez de un recordatorio genérico,
   se explicó la regla técnica exacta (en lenguajes con comentarios de una
   sola línea, todo lo posterior al `#`/`//` en la misma línea física es
   inerte con independencia de los caracteres bidi) y se pidió comprobar
   explícitamente si el payload está en la misma línea que el comentario.
   **Resultado: cambio real.** `risk_score` bajó de 98 a 80, la categoría
   pasó de `escalada_privilegios` a `ofuscacion` (igual que sin RAG), y la
   justificación reconoce explícitamente "la línea completa aparece como
   un comentario en Python debido al '#'".

**Conclusión:** un recordatorio genérico de "verifica antes de puntuar" no
basta -- el modelo necesita la regla técnica *específica* del dominio
(aquí, semántica de comentarios de una sola línea) para aplicar la
verificación de verdad. Esto sugiere que, según se investiguen más
técnicas para el corpus, conviene incluir explícitamente qué comprobación
hace que el patrón *funcione o no* en el diff concreto, no solo describir
la técnica en abstracto.
