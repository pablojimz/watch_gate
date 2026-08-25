# Manual del Sistema RAG de WatchGate

## Metadatos

- **Autor / Responsable**: Equipo de Desarrollo e Infraestructura de WatchGate
- **Estado**: Documento Oficial de Referencia / Producción
- **Ubicación**: `docs/manual_rag.md`
- **Última actualización**: 2026-08-24

---

# 1. Introducción

El sistema **RAG** (*Retrieval-Augmented Generation*) es el componente que
da a la capa semántica de WatchGate el conocimiento que un modelo de
lenguaje generalista **no tiene de serie**: los paquetes maliciosos
publicados esta misma semana, los patrones concretos de las campañas de
ataque a la cadena de suministro conocidas, y el propio historial de
revisión confirmado por humanos de la organización.

En cada análisis de una Pull Request, la capa semántica no le pasa el diff
al LLM "a secas": primero **recupera** los casos de ataque más parecidos al
cambio que se está analizando y los inyecta en el prompt como contexto. Así
el modelo razona sobre el PR con ejemplos reales delante, en vez de solo con
lo que memorizó durante su entrenamiento (que además tiene fecha de corte).

El RAG es local y sin coste de API: usa **ChromaDB** como base de datos
vectorial y **sentence-transformers** (`all-MiniLM-L6-v2`) para generar los
*embeddings* en CPU, sin llamar a ningún servicio externo para el embebido.

---

# 2. Arquitectura

```
+-----------------------------------------------------------------------+
|                        FUENTES DE CONOCIMIENTO                         |
|                                                                       |
|  1. Corpus curado a mano   2. Avisos sincronizados   3. Feedback      |
|     (core/rag/corpus/          (GitHub Advisories        humano        |
|      *.md, versionado)          -> corpus/advisory_*)    (confirmado   |
|                                                          por revisor)  |
+-----------------+---------------------+---------------------+---------+
                  |                     |                     |
                  v                     v                     v
         +--------------------------------------+  +--------------------+
         |  Colección ChromaDB "attack_patterns"|  | Colección          |
         |  (corpus público, compartido)        |  | "feedback_cases"   |
         |                                      |  | (por organización) |
         +------------------+-------------------+  +---------+----------+
                            |                                |
                            +----------------+---------------+
                                             |
                                             v
                          retrieve_relevant_context(diff_summary)
                             - top-k del corpus, DIVERSIFICADO por caso
                             - hueco garantizado para el feedback humano
                                             |
                                             v
                              Prompt de la capa semántica -> LLM
```

## 2.1 Las tres fuentes de conocimiento

| Fuente | Origen | Colección ChromaDB | ¿Versionado en git? |
|--------|--------|--------------------|---------------------|
| **Corpus curado** | Casos escritos a mano en `watchgate/core/rag/corpus/*.md` | `attack_patterns` | Sí |
| **Avisos sincronizados** | API de GitHub Security Advisories (`watchgate rag sync-cves`) | `attack_patterns` | Sí (`advisory_*.md`) |
| **Feedback humano** | Veredictos "correcto"/"falso positivo" del dashboard | `feedback_cases` | No (estado de instancia, bajo `.watchgate/`) |

Las dos primeras conviven en la **misma** colección (`attack_patterns`): son
conocimiento público de casos de ataque. El feedback vive **aparte**
(`feedback_cases`) a propósito — un caso confirmado del propio historial de
revisión es la señal más directa que existe, y no debe competir por hueco en
el top-k contra un corpus público que puede crecer hasta miles de entradas.

## 2.2 Módulos implicados

| Módulo | Responsabilidad |
|--------|-----------------|
| `core/rag/indexer.py` | Trocea el corpus, genera *embeddings* y los persiste en ChromaDB (`build_index`) |
| `core/rag/retriever.py` | Recupera los fragmentos relevantes en cada análisis (`retrieve_relevant_context`) |
| `core/rag/threat_feed.py` | Descarga avisos de GitHub Advisories y los convierte en `.md` del corpus |
| `core/rag/feedback.py` | Incorpora en caliente un caso confirmado por un humano (`add_confirmed_case`) |
| `dashboard/backend/routers/rag.py` | Expone el corpus al dashboard (vista visual del RAG) |
| `dashboard/backend/tasks.py` | Tareas del worker: `run_rag_sync`, `run_feedback_indexing` |

---

# 3. Estructura de un documento del corpus

Cada caso es un fichero Markdown con un formato fijo que tanto el indexado
vectorial como la vista del dashboard saben interpretar. El **prefijo del
título H1** determina el tipo mostrado en el dashboard:

| Prefijo del H1 | Tipo en el dashboard |
|----------------|----------------------|
| `# Caso: ...` | Caso real |
| `# Aviso: ...` | Aviso (CVE/malware) |
| `# MITRE ATT&CK ...` | Técnica MITRE ATT&CK |
| `# Técnica: ...` | Técnica |
| `# Patrón: ...` | Patrón |
| (cualquier otro) | Otro |

Plantilla recomendada para un caso curado:

```markdown
# Caso: nombre descriptivo del incidente (fecha)

## Resumen

Qué pasó, cuándo, a quién afectó y con qué alcance. Este primer párrafo es
el que el dashboard muestra como resumen de la tarjeta.

## Vector de introducción

Cómo entró: cuenta comprometida, typosquat, dependency confusion, script de
build... Los detalles técnicos concretos que un LLM generalista no conoce.

## Patrón a vigilar

1-3 líneas describiendo el patrón CONCRETO que aparecería en un diff. Debe
ser accionable: "un diff que solo añade una línea a package.json apuntando
a un paquete a distancia de edición 1 de uno legítimo", no consejos
genéricos.

Técnica MITRE ATT&CK relacionada: T1195.001 (...), T1027 (...).
```

> **Principio de diseño clave**: el RAG debe darle al modelo *conocimiento
> que no tiene por defecto*. Un documento no debe ser un resumen abstracto
> ("ten cuidado con las dependencias"), sino el detalle concreto y
> verificable de un incidente real y el patrón exacto que lo delataría en un
> diff.

---

# 4. Comandos de la CLI

## 4.1 `watchgate rag reindex`

Reconstruye el índice vectorial completo a partir del corpus local. Hay que
ejecutarlo tras **añadir o editar** cualquier fichero del corpus a mano.

```bash
watchgate rag reindex
# Opcional: ruta alternativa del índice
watchgate rag reindex --index-path /ruta/al/indice
```

## 4.2 `watchgate rag sync-cves`

Descarga avisos reales de la API de **GitHub Security Advisories** al corpus
y reindexa automáticamente si hubo cambios.

```bash
# Por defecto: paquetes maliciosos (type=malware) de npm y pip, 30 por ecosistema
watchgate rag sync-cves

# CVEs curados por GitHub en lugar de solo malware
watchgate rag sync-cves --type reviewed

# Varios ecosistemas y más volumen
watchgate rag sync-cves --ecosystem npm --ecosystem pip --ecosystem rust --limit 100

# Solo descargar, sin reindexar (útil para revisar antes de indexar)
watchgate rag sync-cves --no-reindex
```

| Opción | Valores | Default |
|--------|---------|---------|
| `--ecosystem` (repetible) | `npm`, `pip`, `rubygems`, `maven`, `go`, `rust`... | `npm` y `pip` |
| `--type` | `malware`, `reviewed` | `malware` |
| `--limit` | Máximo de avisos por ecosistema | `30` |
| `--no-reindex` | No reindexar tras descargar | (reindexar) |

**Autenticación**: la API funciona anónima (60 peticiones/hora, suficiente
para un sync normal). Si hay `GITHUB_TOKEN` o `WATCHGATE_GITHUB_TOKEN` en el
entorno, se usa y el límite sube a 5.000/hora.

**Idempotencia**: el mismo aviso siempre acaba en el mismo fichero
(`advisory_<ghsa-id>.md`) y no se reescribe si su contenido no ha cambiado —
ejecutarlo dos veces seguidas no ensucia el árbol de git.

---

# 5. RAG dinámico (actualización automática)

Además de la ejecución manual, WatchGate mantiene el RAG actualizado solo,
por tres vías, sin intervención humana:

## 5.1 Sync periódico de avisos

El `dashboard-backend`, al arrancar y luego cada `N` horas, **encola** en el
worker una tarea `run_rag_sync` que sincroniza los avisos y reindexa si hubo
cambios. El backend solo encola (barato); el trabajo pesado (descarga +
*embeddings* + ChromaDB) corre en el `dashboard-worker`, que es quien usa el
índice en los análisis.

```bash
# En .env — cada cuántas horas (24 por defecto; 0 lo desactiva)
WATCHGATE_RAG_SYNC_INTERVAL_HOURS=24
```

## 5.2 Feedback humano → RAG

Cuando un revisor marca un análisis como **"correcto"** o **"falso
positivo"** en el dashboard, ese veredicto se encola (`run_feedback_indexing`)
y se incorpora a la colección `feedback_cases`. A partir de ese momento, un
PR parecido recuperará ese caso confirmado — con hueco garantizado en el
top-k — y el LLM lo verá al razonar. Así el sistema **aprende del propio
historial de revisión** de la organización.

Es *best-effort*: el feedback ya quedó guardado en la base de datos antes de
encolarse el indexado, así que si Redis está caído el click del revisor no
falla — solo se pierde esa incorporación al RAG (recuperable reindexando).

## 5.3 Reindexado manual

La red de seguridad de siempre: `watchgate rag reindex` reconstruye todo el
índice del corpus desde cero.

---

# 6. Recuperación: cómo se elige el contexto

`retrieve_relevant_context(diff_summary)` (en `retriever.py`) hace, en cada
análisis:

1. **Embebe** el resumen del diff con el mismo modelo cacheado.
2. Consulta la colección de **feedback** de la organización (`feedback_k=1`
   por defecto: hueco garantizado para el caso confirmado más parecido).
3. Consulta el **corpus público** pidiendo de más (`k * 3`) y luego
   **diversifica por caso**: como máximo un fragmento por `case_name`.

El paso de diversificación es importante desde que el corpus incluye decenas
de avisos `advisory_*` que comparten plantilla: sin él, el top-k podía
llenarse con variaciones casi idénticas del mismo documento (o con varios
trozos de un mismo caso largo) y expulsar al segundo y tercer caso *distinto*
que sí aporta contexto nuevo al prompt.

**Aislamiento por organización** (RAG distribuido): si se usa un ChromaDB
compartido entre despliegues (`WATCHGATE_CHROMA_URL`), la colección de
feedback se filtra por `org_id` — el feedback de un tenant nunca se recupera
en el análisis de otro. El corpus público, en cambio, se comparte a
propósito: es investigación de casos de ataque conocidos.

---

# 7. La vista del RAG en el dashboard

El dashboard expone el corpus de forma visual (página **RAG**): una tarjeta
por caso, con su tipo, título y resumen, buscador, y un botón "Ver documento
completo" que abre el Markdown renderizado. Sirve para que un usuario vea de
un vistazo **de qué conocimiento dispone el sistema** al analizar, algo que
antes solo era visible abriendo el repositorio.

Los endpoints (`routers/rag.py`) leen los `.md` directamente, sin cargar
ChromaDB: la vista funciona aunque no se haya ejecutado nunca `rag reindex`.
El `case_id` de la URL se valida contra un patrón cerrado antes de construir
la ruta, para evitar *path traversal*.

---

# 8. Variables de entorno relevantes

| Variable | Efecto | Default |
|----------|--------|---------|
| `WATCHGATE_RAG_SYNC_INTERVAL_HOURS` | Cada cuántas horas se sincronizan los avisos automáticamente (0 = desactivado) | `24` |
| `GITHUB_TOKEN` / `WATCHGATE_GITHUB_TOKEN` | Eleva el límite de la API de Advisories de 60 a 5.000 req/h | (anónimo) |
| `WATCHGATE_CHROMA_URL` / `CHROMA_URL` | Usa un ChromaDB remoto (RAG distribuido) en vez del índice local | (local) |

---

# 9. Recetas rápidas

**Añadir un caso nuevo a mano:**
```bash
# 1. Crear el fichero siguiendo la plantilla de la sección 3
$EDITOR watchgate/core/rag/corpus/mi_nuevo_caso.md
# 2. Reindexar
watchgate rag reindex
```

**Alimentar el corpus con malware real de varios ecosistemas:**
```bash
watchgate rag sync-cves --ecosystem npm --ecosystem pip \
  --ecosystem rubygems --ecosystem rust --limit 150
```

**Comprobar cuántos documentos hay en el corpus:**
```bash
ls watchgate/core/rag/corpus/*.md | wc -l
```

**Forzar una reconstrucción total del índice** (p. ej. tras cambiar de
modelo de *embeddings*):
```bash
rm -rf .watchgate/rag_index
watchgate rag reindex
```

---

# 10. Preguntas frecuentes

**¿Cada análisis descarga avisos nuevos?**
No. El análisis solo *consulta* el índice ya construido (rápido, local). La
descarga de avisos ocurre aparte: manual (`sync-cves`) o periódica (el sync
del worker cada `N` horas).

**¿El RAG llama a alguna API de pago?**
No. El embebido es local (sentence-transformers en CPU) y la API de GitHub
Advisories es gratuita. El único coste de API es el del LLM de la capa
semántica, que es independiente del RAG.

**¿Qué pasa si no se ha ejecutado `rag reindex` nunca?**
El análisis funciona igual, sin contexto RAG (la recuperación devuelve una
lista vacía sin error). La vista del dashboard también funciona, porque lee
los `.md` directamente.

**¿El feedback humano se pierde al reiniciar?**
No mientras exista `.watchgate/rag_feedback/` y el índice. Es estado de
instancia (no se versiona en git), pero persiste entre reinicios del worker.
