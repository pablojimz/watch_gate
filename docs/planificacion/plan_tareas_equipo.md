# Reparto de tareas del equipo

Basado en `docs/WatchGate_spec_implementacion_IA.md` (spec de implementación). Los criterios de aceptación de cada tarea son literales de la spec, no inventados — cuando una tarea dice "hecho cuando X", es el mismo test que un agente de codificación (o un revisor) puede ejecutar para verificarla.

**Reparto de líneas (actualizado, ya no coincide con la memoria sección 5.1):** Pablo Ayllón García y Pablo Jiménez Castro han intercambiado su línea respecto al reparto original. Javier Martín Jurado no cambia.

| Línea | Responsable | Alcance |
|---|---|---|
| 1 — Núcleo, orquestador, agregador | **Pablo Ayllón García** | `diffparser`, `aggregator`, `orchestrator`, `cost_control` |
| 2 — Reputación y semántica | **Javier Martín Jurado** | `reputation_layer`, RAG, capa semántica completa |
| 3 — Estática/dependencias y dashboard | **Pablo Jiménez Castro** | `static_layer`, `deps_layer`, dashboard (backend + frontend) |

El criterio de agrupación sigue siendo el mismo: cada capa de análisis implementa `AnalysisLayer.analyze(diff, metadata) -> LayerResult` (spec §3) y solo depende del contrato de `models.py` — nunca de las capas de las demás. Ninguna tarea de una persona bloquea a otra fuera de los tres puntos listados al final.

---

## Fase 0 — Contrato compartido (bloqueante, ~1 día, un solo responsable) ✅ HECHO

Nadie más puede empezar código real hasta que esto esté cerrado.

- [x] **`watchgate/core/models.py`** (§1) — `FileChange`, `CommitAuthor`, `NormalizedDiff`, `LayerResult`, `AggregatedResult`, `ReputationMetadata`, enums `RiskCategory`/`Confidence`/`Semaforo`.
  **Hecho cuando:** `AggregatedResult.model_dump_json()` es el único contrato JSON que consumen el comentario de PR y el dashboard; ningún otro módulo redefine estas clases. ✅ Verificado en `tests/unit/test_models.py` (roundtrip JSON, límites de `risk_score`, caso semántico completo).
- [x] **`watchgate/core/layers/base.py`** (§3) — `AnalysisLayer` (ABC), `LAYER_REGISTRY`, decorador `register_layer`, `safe_analyze`.
  **Hecho cuando:** `tests/unit/test_architecture.py` con `import-linter` (contrato `Layers`) falla el build si algo bajo `core/` importa `adapters/` o `dashboard/`. El orquestador nunca importa una capa concreta por nombre, solo instancia desde `LAYER_REGISTRY`. ✅ El test no solo comprueba que el contrato pasa hoy, sino que introduce una violación real a propósito y verifica que el linter la detecta.

**Responsable:** Pablo Ayllón García (línea 1, núcleo).

**Estado:** implementado y verificado — `pytest` (14/14), `ruff check`, `ruff format --check` y `mypy --strict` en verde sobre `watchgate/core/`. Detalle de entorno y verificación en la nota al final de este documento.

En cuanto esto está mergeado, las tres líneas arrancan **en paralelo**.

---

## Fase 1 — Trabajo en paralelo por línea

### Línea 1 — Pablo Ayllón García (núcleo, orquestador, agregador, CLI) ✅ HECHO

- [x] **`diffparser.py`** (§2) — `parse_diff(repo_path, base_sha, head_sha) -> NormalizedDiff`, sin red, usando `GitPython`.
  Casos límite a testear explícitamente: diff vacío (`base_sha == head_sha`), archivo renombrado sin cambio de contenido, archivo binario (`is_binary=True`), historial con merge commits (usar `first_parent=True` al iterar).
  **Hecho cuando:** test con repo git real generado en `tempfile.mkdtemp()` (2 commits) devuelve exactamente los ficheros y autores esperados. ✅ Verificado en `tests/unit/test_diffparser.py`.

- [x] **`aggregator.py` + `comment_template.py`** (§10) — `aggregate()`, `_semaforo()`, plantilla Jinja2 del comentario.
  **Hecho cuando:** con el ejemplo exacto de la memoria (estática 20, deps 10, reputación 40, semántica 85; pesos 0.25/0.20/0.15/0.40) el resultado es `score == 47` y `semaforo == AMARILLO`. Este test de regresión no debe fallar nunca. ✅ Verificado en `tests/unit/test_aggregator.py`.

- [x] **`orchestrator.py`** (§9) — `run_analysis()` con `ThreadPoolExecutor`, filtro únicamente por `weight > 0` (sin ningún otro `if` de qué capa ejecutar).
  **Hecho cuando:** test con 4 capas *fake* (una con latencia simulada de 2s) muestra tiempo total ~2s (paralelo), no ~8s (secuencial). ✅ Verificado en `tests/unit/test_orchestrator.py`.

- [x] **`cost_control.py`** (§8) — `CostController` (estimación de tokens, truncado, cache SQLite, presupuesto mensual). Esquema exacto: `semantic_cache(diff_hash, output_json, created_at)`, `token_usage(repo, month, tokens_used)`.
  **Hecho cuando:** con presupuesto agotado simulado, `SemanticLayer.analyze` devuelve `skipped=True` **sin** llamar al LLM (mock HTTP con `call_count == 0`). ✅ Verificado en `tests/unit/test_cost_control.py`.

- [x] **`cli.py`** (§9, §12) — CLI con subcomandos `watchgate analyze` (análisis de diff, formato Markdown o JSON, cortocircuito) y `watchgate rag reindex`.
  **Hecho cuando:** ejecución de `watchgate analyze` y `watchgate rag reindex` parsea argumentos y ejecuta el pipeline. ✅ Verificado en `tests/unit/test_cli.py`.

### Línea 2 — Javier Martín Jurado (reputación y semántica) ✅ HECHO

- [x] **`reputation_layer.py`** (§6) — tabla de puntuación por reglas (no ML), suma con tope 100, capa que **nunca** hace llamadas HTTP (toda la metadata llega resuelta del adaptador).
  Señales exactas: cuenta <30 días (+30), 0 contribuciones previas (+20), email no verificado (+25), repo firma habitualmente pero commit no firmado (+30), firmado con clave nunca vista (+40).
  **Hecho cuando:** metadata simulando Atomic Arch (cuenta de 2 días, 0 contribuciones, email no verificado) da `risk_score >= 75`. ✅ 7 tests, incluido el caso Atomic Arch (75) y el tope en 100.

- [x] **`rag/indexer.py` + `rag/retriever.py` + corpus** (§7.4) — corpus en `.md` (`xz_utils.md`, `prt_scan.md`, `atomic_arch.md` + 3 entradas de MITRE ATT&CK: T1195, T1027, T1548). Embeddings con `sentence-transformers` (`all-MiniLM-L6-v2`, CPU, sin API externa), persistidos en ChromaDB local (colección `attack_patterns`).
  **Hecho cuando:** `build_index()` genera la colección persistente; `retrieve_relevant_context(diff_summary, k=3)` devuelve 3 fragmentos con `case_name`. ✅ Probado de extremo a extremo con el modelo de embeddings real, no mockeado.

- [x] **`_semantic/prompting.py` + `_semantic/tools.py`** (§7.1–7.2) — prompt de sistema literal de la spec, few-shot cargado de `datasets/few_shot/*.json` (2 ejemplos añadidos: refactor benigno y `curl|bash` en PKGBUILD), 3 tools (`lookup_package_registry`, `get_commit_history`, `fetch_referenced_file`) con `ToolCallBudget(max_calls=3)`.
  **Hecho cuando:** al agotar el presupuesto de tool calls, el sistema fuerza `"Responde ahora con el JSON final"` y el modelo no puede pedir una 4ª herramienta. ✅ Verificado en `test_semantic_client.py`.

- [x] **`_semantic/client.py` + `_semantic/layer.py`** (§7.3, §7.5) — `LLMClient` (ABC) + `AnthropicClient` (**decisión humana ya tomada:** Anthropic). Reintento único si el JSON no parsea; si falla dos veces, `skipped=True, skip_reason="LLM no devolvió JSON válido tras 2 intentos"`.
  **Hecho cuando:** con un `LLMClient` *fake* inyectado (sin llamar a ninguna API real), el flujo completo RAG → prompt → parseo → cache funciona con una respuesta simulada. ✅ `test_semantic_layer.py::test_full_flow_rag_prompt_parse_cache`.

**Nota de integración con `cost_control.py` (Línea 1):** `_semantic/layer.py` no importa `watchgate.core.cost_control` directamente — depende de un `CostControllerLike` (`Protocol` estructural con `budget_remaining`, `estimate_tokens`, `get_cached`, `store_cached`, `record_usage`). Cuando Pablo Ayllón implemente `CostController` con esos mismos métodos, se integra pasando la instancia real al constructor de `SemanticLayer`, sin tocar `layer.py`.

**Desviación menor respecto al pseudocódigo de la spec (documentada en el docstring de `client.py`):** `LLMClient.complete_structured` añade un parámetro `tool_executor` que no aparece en el esqueleto de §7.3 — sin él, el cliente no tenía forma de *ejecutar* las tools (la spec solo describe pasarle los esquemas JSON, no los callables). `layer.py` construye ese executor con acceso a las funciones reales de `tools.py`.

**Cobertura:** 99% sobre todo `core/` (62 tests en total tras la revisión). Los pocos huecos que quedan son deliberados: el constructor real de `AnthropicClient` (evita golpear la API real en tests) y el bloque `if __name__ == "__main__"` de `indexer.py`.

**Revisión posterior (misma línea, antes de integrar):** tres pasadas encontraron y arreglaron 8 problemas reales, todos con test de regresión:
1. `indexer.py` reindexaba con `upsert`, así que si un documento del corpus encogía entre dos ejecuciones, sus fragmentos sobrantes quedaban huérfanos en la colección. Ahora cada `build_index()` borra la colección antes de reconstruirla.
2. `FEW_SHOT_EXAMPLES` se cargaba desde disco pero nunca se inyectaba en ningún prompt — estaba muerto. `build_system_prompt()` ahora los añade al final del prompt de sistema.
3. El `TOOL_SCHEMA` de `fetch_referenced_file` le pedía `repo_path` al LLM, pero el executor de `layer.py` siempre usa el `repo_path` real del diff (por seguridad, nunca uno propuesto por el modelo) — el esquema ya no se lo pide, para no confundir al modelo con un parámetro que se ignora.
4. `record_usage()` solo contabilizaba el `user_prompt`; ahora también cuenta el `system_prompt`. Sigue sin poder contabilizar las idas y vueltas de tool-calls ni los tokens de salida, porque `LLMClient.complete_structured` no expone el consumo real de la conversación — documentado como limitación conocida en el propio código, a resolver si se decide exponer `usage` desde el cliente LLM.
5. **Bucle sin fin en `client.py`:** si el modelo seguía pidiendo `tool_use` incluso con `tools=[]` (presupuesto agotado, comportamiento adversarial o fallo del proveedor), la conversación no tenía tope de turnos — solo tope de *ejecuciones* de tools. Reproducido con un cliente fake que siempre responde `tool_use`: se colgaba. Añadido un tope duro (`max_tool_calls + 3` turnos) que corta con `SemanticParsingError` en vez de repetir llamadas a la API sin límite.
6. `lookup_package_registry` solo capturaba `httpx.HTTPError`; un 200 con cuerpo no-JSON (proxy caído, mantenimiento) lanza `json.JSONDecodeError`, que no hereda de `HTTPError` y se habría escapado sin capturar. Añadido a la captura.
7. **Inyección de opciones en `fetch_referenced_file`:** `ref`/`path` los propone el LLM y se pasaban directos a `git show`; un valor que empezara por `-` se interpreta como una opción del comando en vez de como revisión/ruta. Probado con `git show` real: sin protección, falla con "unrecognized argument" en el mejor caso, pero no hay garantía de que ningún flag reconocido de `git show` tenga efectos secundarios. El separador `--` (mitigación estándar) **no vale aquí** porque cambia el significado de la sintaxis `rev:path` (pasa a interpretarse como pathspec) — se valida y rechaza en su lugar cualquier spec que empiece por `-`, antes de invocar git.
8. **`_build_tool_executor` (`layer.py`) no capturaba errores del propio dispatch:** si el LLM llamaba a una tool con argumentos incompletos (p. ej. a `lookup_package_registry` sin `ecosystem`), el `**tool_input` revienta con `TypeError` sin capturar. `safe_analyze` (Fase 0) lo habría amortiguado a nivel de sistema, pero el contrato propio de `AnalysisLayer.analyze` ("nunca debe lanzar excepción no controlada", spec §3) no se cumplía por sí solo. Ahora el dispatcher envuelve cada llamada y devuelve el error como resultado de la tool, igual que un fallo de red.

**Detalle menor de higiene de datos:** el ejemplo few-shot de `curl | bash` usaba `185.199.108.153`, que es una IP real del rango de GitHub Pages — sustituida por un dominio de documentación reservado (`.example`, RFC 2606) para no usar infraestructura real de un tercero como ejemplo de servidor malicioso.

**Extensión posterior (RAG dinámico y LLM multi-proveedor), no exigida por la spec pero construida sobre el mismo diseño:**

1. **Bucle de feedback humano → RAG (`rag/feedback.py`):** cuando el dashboard confirme el veredicto de un análisis (verdadero/falso positivo), `add_confirmed_case(case_id, title, narrative, verdict)` trocea el caso, lo embebe y lo *upsertea* en la colección existente **sin rehacer el corpus estático completo** (a diferencia de `build_index()`). Si se reenvía el mismo `case_id` con menos fragmentos que antes, borra primero los huérfanos de la versión previa — mismo problema que el punto 1 de la revisión anterior, resuelto ahora a nivel de un solo documento. `RetrievedFragment` gana `origin`/`verdict`, y `prompting.py` renderiza esos casos como "caso propio confirmado por revisión humana", una señal más fuerte que un caso histórico genérico.
2. **`LLMClient` deja de tener una única implementación:** `_semantic/llm_providers.py` añade `GeminiClient` (SDK oficial `google-genai`, verificado campo a campo contra el paquete instalado, sin poder probarlo aún contra la API real por falta de credenciales) y `OpenAICompatibleClient` (protocolo de chat completions de OpenAI — el que hablan Ollama, llama.cpp server, LM Studio y vLLM al servir modelos en local, sin depender de un SDK propietario). `_semantic/llm_factory.py` selecciona la implementación vía `WATCHGATE_LLM_PROVIDER` (`anthropic`/`gemini`/`local`); `SemanticLayer` no cambia, porque ya recibía el `LLMClient` por constructor.
3. **Cuarta tool opcional, `check_file_reputation` (VirusTotal):** calcula el SHA256 real de un fichero referenciado en una revisión (mismo mecanismo y misma protección contra inyección que `fetch_referenced_file`) y consulta su reputación en VT — pensada para el propio caso XZ Utils, un blob/binario ya conocido como malicioso colándose en un fichero de test. Solo se ofrece al LLM (`build_tool_schemas()`) si hay `WATCHGATE_VT_API_KEY` configurada; sin ella, ni se intenta la llamada. **Probado en vivo** contra la API real de VirusTotal (fichero de test EICAR, 64/75 motores lo detectan) — funciona de extremo a extremo, no solo con mocks.
4. **Consulta OSV en vivo, no solo cuando el LLM decide pedirla (`detect_new_python_dependencies` / `gather_dependency_findings` en `tools.py`):** antes de construir el prompt, `layer.py` detecta paquetes PyPI nuevos añadidos en `requirements*.txt` (heurística deliberadamente estrecha — parsear manifests de verdad es tarea de `deps_layer.py`, Línea 3) y consulta OSV para cada uno; solo los que tienen vulnerabilidades reales entran en un bloque nuevo del prompt de sistema. Es el mismo patrón "eager" que ya usa el RAG (consulta automática de Python, no una tool que el LLM tiene que pensar en pedir), complementario a `lookup_package_registry` (que sigue existiendo para que el LLM investigue algo puntual que esta heurística no capturó).
5. **Casos reales añadidos al corpus RAG y a los few-shot, centrados en Python y Docker (los ecosistemas que le interesan al equipo ahora mismo):** `pypi_ctx_env_exfiltration.md` (caso real `ctx`, GHSA-4g82-3jcr-q52w, encontrado vía la API pública de OSV.dev, sin necesidad de key de pago) y `docker_typosquatted_base_images.md` (patrón documentado de imágenes de Docker Hub troyanizadas/typosquatted, centrado en lo que sí es visible en un diff: cambios de `FROM` a un tag mutable, `RUN curl | sh` en el build). Ningún binario ni malware ejecutable se ha descargado ni se guarda en el repo — todo es texto de casos públicos, con cualquier infraestructura viva sustituida por dominios de ejemplo.
6. **Bug de entorno recurrente (no del código):** en esta máquina, al vivir el repo en `~/Desktop` (con iCloud), macOS a veces vuelve a marcar los `.pth` del venv como `hidden` tras cada `poetry install`, y Python 3.11+ los ignora sin avisar — rompe la importación de `watchgate` fuera de `python -c` ejecutado desde la raíz del repo (incluido `pytest`). Arreglado de forma duradera con `pythonpath = ["."]` en `[tool.pytest.ini_options]` (`pyproject.toml`), independiente de que el flag esté puesto o no. `scripts/smoke_test_linea2.py` (que se ejecuta suelto, no vía pytest) se protege aparte insertando la raíz del repo en `sys.path` al principio del propio script.
7. **`scripts/smoke_test_linea2.py`:** bypass deliberado de Línea 1 para poder lanzar `ReputationLayer` + `SemanticLayer` de verdad contra un repo git local, sin esperar a `cost_control.py` ni al orquestador real. Incluye un `_ToyCostController` en memoria (presupuesto infinito, sin persistencia, claramente marcado como no-producción) y un parseo crudo de `git diff` a `NormalizedDiff`. Probado de extremo a extremo contra un repo desechable: el parseo del diff y `ReputationLayer` funcionan correctamente; `SemanticLayer` falla exactamente donde debe (sin `WATCHGATE_LLM_API_KEY` configurada, sin ningún otro fallo oculto).

**Revisión posterior de esta extensión (misma línea, antes de seguir):** una pasada más encontró y arregló 4 problemas reales:
1. **`gather_dependency_findings` sin tope de peticiones:** a diferencia de `lookup_package_registry` como tool del LLM (acotada por `ToolCallBudget(max_calls=3)`), la consulta automática por PR no tenía límite — un `requirements.txt` con muchas líneas nuevas (p. ej. un `pip freeze` inicial con 100 paquetes) dispararía igual de llamadas HTTP secuenciales, cada una con hasta 10s de timeout, bloqueando el análisis varios minutos en el peor caso. Añadido `_MAX_DEPENDENCY_CHECKS = 10`.
2. **`OpenAICompatibleClient` no capturaba JSON malformado en los argumentos de una tool call:** `json.loads(function["arguments"])` podía lanzar `json.JSONDecodeError` sin capturar, tirando abajo toda la conversación. Los modelos locales (el caso de uso de este cliente) son menos fiables generando tool-calling bien formado que Anthropic/Gemini, así que este fallo es más probable aquí que en los otros clientes. Ahora se trata igual que un fallo de dispatch: se le devuelve el error como resultado de la tool y la conversación continúa.
3. **Inyección de ruta en `add_confirmed_case` (`rag/feedback.py`):** `case_id` se usaba tal cual como nombre de fichero (`feedback_dir/{case_id}.md`). Probado en vivo: `case_id="../../etc/passwd"` resuelve fuera del directorio de feedback. Añadida una validación de charset seguro (`[A-Za-z0-9_-]+`) que rechaza cualquier otro valor con `ValueError` antes de tocar el sistema de ficheros.
4. **Dominio real citado sin defanging** en `pypi_ctx_env_exfiltration.md`: la URL del C2 (`anti-theft-web.herokuapp.com`) viene citada literal de la advisory oficial (GHSA-4g82-3jcr-q52w), no fabricada, pero seguía siendo un enlace histórico clicable. Defangeado (`hxxps://...[.]herokuapp[.]com`) por el mismo criterio de higiene de datos que ya se aplicó al ejemplo few-shot de PKGBUILD.

**Optimización de tokens de la capa semántica (`prompting.py`), sin quitar contexto ni depender de un proveedor concreto:**

Comprobado con una consulta RAG real contra el propio corpus (`xz_utils`): pedir k=3 fragmentos a veces devuelve dos chunks del mismo documento, y por el solape deliberado de `_CHUNK_OVERLAP_CHARS` en `indexer.py` (para no cortar frases a la mitad al trocear), ambos chunks comparten un trozo de texto literal -- se estaba enviando esa misma frase dos veces al LLM. Dos medidas, aplicadas solo a los fragmentos RAG (nunca al diff bajo revisión, eso no se toca):

1. **`_strip_known_overlap`:** si el principio o el final de un fragmento coincide con el final/principio de otro fragmento ya renderizado del mismo caso (`case_name`), quita esa parte repetida. La recuperación por similitud no garantiza el orden del documento, así que se comprueban las dos direcciones. Nunca compara fragmentos de casos distintos entre sí (un solape ahí sería casualidad, no chunking).
2. **`_normalize_whitespace`:** colapsa líneas en blanco repetidas y espacios finales de línea en el markdown de los fragmentos.

Verificado con datos reales de este propio índice: dos chunks de `xz_utils` que compartían el heading `## Por qué es relevante para WatchGate` (38 caracteres solapados) ahora solo lo incluyen una vez, sin perder ninguna frase exclusiva de ninguno de los dos fragmentos (comprobado explícitamente en el test de regresión).

**Ampliación del corpus con técnicas/metodologías que faltaban** (además de los casos concretos de PyPI/Docker ya añadidos), buscando huecos reales en lo ya cubierto:

- `trojan_source_unicode_bidi.md` — caracteres de control Unicode bidireccional (CVE-2021-42574, Boucher & Anderson, Universidad de Cambridge) que reordenan visualmente el código sin cambiar lo que el compilador ejecuta; el ejemplo por excelencia de por qué no basta con "leer" el diff.
- `solarwinds_orion_build_compromise.md` — SUNBURST (diciembre 2020), el caso de referencia de compromiso del **sistema de build** en vez del código fuente: no hay ningún diff que revisar porque el backdoor se insertó en la compilación, no en git. Documenta el límite explícito de lo que un analizador de diffs puede cubrir por sí solo.
- `dependency_confusion.md` — técnica de Alex Birsan (2021), distinta del typosquatting: mismo nombre exacto que un paquete interno, publicado en el registro público con versión más alta, para que el gestor de paquetes lo resuelva por error. Conecta directamente con `gather_dependency_findings` (Fase 2 del RAG dinámico).

Con few-shot a juego para los tres (`malicious_trojan_source_bidi_override.json`, `malicious_dependency_confusion.json`; SolarWinds no tiene few-shot propio porque el vector no es visible en un diff, es justamente el punto del caso). 9 ejemplos few-shot en total ahora, cubriendo 4 categorías de `RiskCategory`.

**Investigación de una ingesta automática de CVEs/paquetes maliciosos (Fase 3 del RAG dinámico), con resultado honesto:** se pidió una vía para mantener el corpus actualizado con CVEs sin intervención manual. Antes de construir nada, se verificó qué hay disponible de verdad:

- La comprobación de dependencias (`lookup_package_registry`, `gather_dependency_findings`, `check_file_reputation`) **ya consulta la API en vivo en cada llamada** — nunca hay un CVE cacheado ni una foto fija; esta parte ya estaba resuelta sin cambios.
- Se probó en vivo el feed masivo de OSV de paquetes maliciosos (`https://osv-vulnerabilities.storage.googleapis.com/PyPI/all.zip`, real, ~32MB, actualizado a diario) pensando en generar automáticamente entradas de corpus a partir de él. Resultado tras inspeccionar las 11.606 entradas de PyPI: solo **7** tienen una descripción narrativa real; el resto es metadata de escáner automático (nombre, versión, hash) sin ninguna historia que aportarle al LLM como contexto. Construir una ingesta automática completa para esto no compensaba el esfuerzo.
- Se añadieron esas 7 entradas reales a mano, agrupadas por patrón en vez de un fichero por caso (varias comparten el mismo canal de exfiltración):
  - `pypi_telegram_c2_exfiltration_cluster.md` — 6 paquetes PyPI confirmados maliciosos (`costrar`, `nasrtox`, `requestn`, `tensorfioi`, `ilovenyxx`, `ilovenyxxbait`) que usan la API de bots de Telegram como canal de exfiltración en vez de infraestructura propia — un patrón recurrente, no un caso aislado.
  - Extensión de `dependency_confusion.md` con el caso real `sympy-dev` (`MAL-2026-450`): typosquatting del paquete popular `sympy`, descarga y ejecución de código remoto — variante emparentada pero distinta de la confusión de dependencias (imita un paquete público conocido, no uno interno filtrado).

**Registro persistente + validación contra casos difíciles de verdad (`scripts/smoke_test_linea2.py`):**

- El script ahora registra cada ejecución (`--label`, `--log-path`, `--no-log`) en un JSONL (`.watchgate/semantic_layer_log.jsonl`, gitignored) con el diff probado, qué proveedor/modelo respondió, y el resultado completo de ambas capas -- un rastro consultable sin repetir la llamada a la API.
- Probado con 3 casos deliberadamente difíciles contra Gemini real (sin VirusTotal, para aislar el razonamiento del propio LLM):
  1. **Trojan Source real** (caracteres Unicode bidireccionales de verdad insertados en el diff, no descritos): Gemini identificó los codepoints exactos (`U+202E`, `U+2066`/`U+2069`), nombró la técnica y el CVE (Trojan Source, CVE-2021-42574) y explicó la lógica oculta de escalada de privilegios. `risk_score=98`, confianza alta.
  2. **Payload base64 con `exec()`** (reverse shell real hacia una IP de documentación RFC 5737, nunca infraestructura real): decodificó el payload y describió exactamente el host/puerto de destino y el comportamiento de shell interactiva. `risk_score=99`, categoría `backdoor`.
  3. **Caso de calibración, benigno pero técnico** (carga dinámica de plugins con `importlib`/`pkgutil`, un patrón de diseño legítimo): correctamente clasificado como no malicioso, `risk_score=10`, categoría `ninguna` -- confirma que el sistema no dispara falsos positivos solo por ver código "avanzado".

**Colecciones de ChromaDB separadas + corpus ampliado a 20 casos reales:**

Tras el hallazgo de que el RAG mejora la calibración pero puede sesgar la severidad por el nombre de una técnica conocida (ver comparativa con/sin RAG, `docs/evaluacion_ia/rag_ablation_benchmark.md`), se pidió ampliar el corpus de verdad y separar el feedback humano del corpus público en colecciones distintas de ChromaDB, no solo por metadata dentro de una:

- **`feedback_cases`** (nueva colección, `indexer.py`/`feedback.py`): `add_confirmed_case()` ya no escribe en `attack_patterns`, sino en su propia colección. Motivo: un caso confirmado del propio historial de revisión es la señal más directa que existe, y no debería competir por hueco en el top-k contra un corpus público que puede crecer mucho.
- **`retriever.py` rediseñado**: `retrieve_relevant_context()` consulta ambas colecciones por separado y combina resultados, con **hueco garantizado** para el feedback (`feedback_k=1` por defecto) que no desplaza ni es desplazado por los `k` resultados del corpus público. Verificado con test explícito: con el corpus lleno (3/3 huecos ocupados) más un caso de feedback, salen los 4, ninguno pisa al otro.
- **Corpus público ampliado de 12 a 20 documentos**, con 8 casos reales nuevos, cada uno verificado contra la API pública de OSV.dev antes de escribirlo (salvo dos, de conocimiento público muy bien documentado): `event_stream_flatmap_stream_npm.md`, `coa_rc_npm_maintainer_compromise.md`, `node_ipc_protestware.md`, `colors_faker_maintainer_sabotage.md`, `rest_client_rubygems_backdoor.md`, `ultralytics_pypi_release_compromise.md` (destaca: el código malicioso solo estaba en el artefacto de PyPI, nunca en el repositorio de GitHub — mismo límite estructural que SolarWinds, a escala de un solo paquete), `polyfill_io_cdn_compromise.md` y `codecov_bash_uploader_compromise.md`. Se investigaron más candidatos (npm, RubyGems, PyPI) de los que se acabaron usando -- solo entraron los que tenían narrativa real verificable, mismo criterio que en la ampliación anterior.
- 132 tests en verde, mypy/ruff limpios en todo lo propio de Línea 2 (el resto de errores de mypy/ruff que aparecen al correr sobre todo el repo son de ficheros de otras líneas, no tocados).

**Ampliación con datos reales de MITRE ATT&CK (no solo texto propio):** se comprobó que el bundle STIX oficial de MITRE (`github.com/mitre/cti`, ~47MB, 858 técnicas del Enterprise ATT&CK) es real, accesible y -- a diferencia del volcado de OSV -- sí tiene descripciones en prosa genuinas, no solo metadata. Filtrando por relevancia real para revisión de diffs (se descartaron ~850 técnicas sin relación con el caso de uso: movimiento lateral, captura de pantalla, etc.), se añadieron 3 técnicas nuevas con la descripción oficial de MITRE como base, más análisis propio de por qué importan para WatchGate:

- `attck_t1195_001_compromise_dependencies.md` (Compromise Software Dependencies and Development Tools) -- distinta de T1195.002 ya cubierta; cita explícitamente pip/npm, *revival hijacking* de paquetes abandonados y el "gusano" de GitHub Actions de 2023 como patrón documentado por el propio MITRE, no hipotético.
- `attck_t1078_valid_accounts.md` (Valid Accounts) -- conecta los casos de compromiso de cuenta de mantenedor (`coa`/`rc`, `rest-client`, `ctx`) con la razón de fondo por la que la capa de reputación no puede fiarse de una sola señal aislada. De paso queda anotado un hueco real: MITRE señala explícitamente el riesgo de cuentas *inactivas reactivadas*, patrón que la capa de reputación actual no distingue todavía de una cuenta simplemente antigua.
- `attck_t1584_compromise_infrastructure.md` (Compromise Infrastructure) -- conecta polyfill.io, Codecov y el cluster de Telegram bajo el mismo principio: comprometer algo en lo que el proyecto ya confía por referencia externa, sin tocar el repositorio objetivo en absoluto.

Corpus público final: **23 documentos** (20 + estas 3), 82 fragmentos indexados. 132 tests siguen en verde tras el reindexado.

**Fix del hallazgo de la comparativa con/sin RAG (`docs/evaluacion_ia/rag_ablation_benchmark.md`), probado contra Gemini real:** un recordatorio genérico en el prompt ("verifica el efecto antes de puntuar por el nombre de una técnica") no cambió nada -- mismo `risk_score=98` de antes. Lo que sí funcionó fue explicar en el propio documento del corpus (`trojan_source_unicode_bidi.md`) la regla técnica exacta (en lenguajes de comentario de una sola línea, todo lo posterior al `#`/`//` en la misma línea física es inerte pase lo que pase con los caracteres bidi) y pedir esa comprobación en concreto: `risk_score` bajó de 98 a 80 y la categoría pasó de `escalada_privilegios` a `ofuscacion` (igual que sin RAG), reconociendo explícitamente en la justificación que la línea es un comentario en Python. 133 tests en verde.

**`watchgate/cli.py` implementado de verdad (estaba vacío, solo un docstring, pese a que `pyproject.toml` ya declaraba el entry point `watchgate = "watchgate.cli:main"`):** `watchgate rag reindex` es responsabilidad clara de Línea 2 (§7.4) y ya funciona de extremo a extremo -- probado con el índice real (84 fragmentos). `watchgate analyze` se deja declarado con `--help` funcionando pero devuelve error explícito (exit 1) en vez de fingir que funciona: depende del adaptador de GitHub Action (§12) y del wiring completo orchestrator/cost_control/config, que no es responsabilidad de esta línea. 5 tests nuevos invocando `main()` directamente (no el binario, para no depender del script de consola). 156 tests en verde.

**Cobertura al 100% en todos los ficheros propios de Línea 2** (antes 93-99% con huecos reales, no solo cosméticos): revisando línea a línea qué faltaba, se encontraron 5 ramas sin ejercitar de verdad -- `layer.py` nunca probaba que `_dispatch_tool` enrutara a `check_file_reputation` (solo la función aislada en `tools.py`); `llm_providers.py` tenía el caso de doble fallo de JSON probado para Anthropic y el cliente local, pero no para Gemini (asimetría real entre los tres proveedores); `prompting.py` solo probaba el solape en una dirección (prefijo), no la otra (sufijo) -- justo la rama que arregló el bug real de `xz_utils` de la sesión anterior; `retriever.py` no distinguía "colección ausente" de "colección existente pero vacía" (mismo código, casos distintos). Ninguno de los 5 era un bug nuevo -- simplemente no estaban verificados. 160 tests en verde, mypy --strict y ruff limpios.

**Revertido tras el merge con `origin/main`:** el commit `417fff1` (Línea 1) envolvió `retrieve_relevant_context()` entera en un `except Exception: return []`, y añadió guards `try/except ImportError` para `chromadb`/`langchain_text_splitters` en `indexer.py`/`feedback.py`. Los dos se han deshecho: (1) el `except` genérico de `retriever.py` no protegía nada que no protegiera ya el `except` acotado de `_query_collection` (la única falla real posible ahí -- colección inexistente --, verificado en vivo que `chromadb.PersistentClient` nunca lanza aunque el `index_path` no exista todavía), y de paso silenciaba en falso "no hay contexto RAG" cualquier bug real en la generación de embeddings o en el propio `_query_collection`; (2) `chromadb`/`sentence-transformers`/`langchain-text-splitters` siguen siendo dependencias obligatorias en `pyproject.toml` (sin tocar), así que esos `except ImportError` nunca pueden saltar en un entorno bien instalado -- manejo de errores para un escenario que no puede pasar. 167 tests en verde, mypy --strict y ruff limpios tras revertir.

### Línea 3 — Pablo Jiménez Castro (estática/dependencias y dashboard)

- [ ] **`static_layer.py` + reglas** (§4) — Semgrep (`subprocess`) + `yara-python`. `risk_score = max(...)` de las severidades disparadas, **nunca suma** (regla explícita: evita inflar el score por volumen de hallazgos menores).
  Reglas Semgrep exactas a escribir en `rules/semgrep/watchgate.yml`:
  - [ ] `eval-exec-dynamic` (ERROR)
  - [ ] `shell-true-subprocess` (ERROR)
  - [ ] `curl-pipe-shell` (ERROR)
  - [ ] `privilege-escalation-write` (ERROR)
  - [ ] `network-call-in-build-script` (WARNING)

  Reglas YARA en `rules/yara/obfuscation.yar`:
  - [ ] `long_base64_blob` (cadena base64 >200 caracteres contiguos)
  - [ ] `hex_encoded_shellcode_pattern` (entropía de Shannon > 4.5 bits/byte)

  **Hecho cuando:** fixture `benign_refactor` da `risk_score < 20`; fixture `malicious_eval_base64` da `risk_score >= 60`.

- [ ] **`deps_layer.py` + `layers/_shared.py`** (§5) — sub-parsers `package.json`/`requirements.txt`/`PKGBUILD`, consulta OSV (cacheada en SQLite, TTL 24h), typosquatting vía `rapidfuzz` contra `datasets/typosquat_reference/<ecosistema>.txt`. `_shared.py` extrae la ejecución de Semgrep/YARA sobre texto para reutilizarla en scripts de instalación, sin duplicar código con `static_layer`.
  **Hecho cuando:** una dependencia a distancia Levenshtein ≤2 de `"lodash"` (p. ej. `"1odash"`) da `risk_score >= 75`. Un fallo de red a OSV **no** sube el score, solo se anota como "no verificable".

- [ ] **`dashboard/backend/`** (§13) — `db.py` (esquema exacto `pr_scores` + `repo_roles`), `auth.py` (OAuth GitHub + segunda vía OIDC genérica con `authlib`, cookie de sesión firmada), `routers/scores.py` + `routers/feedback.py`.
  Tabla de permisos exacta a implementar en `require_role`: ver histórico (los 3 roles), ajustar pesos/umbrales (admin + mantenedor en sus repos), resolver feedback (admin + mantenedor), gestionar accesos (solo admin).
  **Hecho cuando:** test de integración con `TestClient` simulando los 3 roles contra los 4 endpoints da 403 exactamente donde la tabla dice ✗.

- [ ] **`dashboard/frontend/`** — React + Vite + TypeScript. Páginas: `/login`, `/repos`, `/repos/:repo` (gráfico `recharts` + tabla expandible por capa), `/repos/:repo/feedback` (solo rol ≥ mantenedor), `/admin` (solo admin_organización).
  Dependencia interna a esta misma línea (backend propio), no cruza con nadie más.

---

## Fase 2 — Integración (al final, depende de que la Fase 1 esté cerrada)

Coordinado por Pablo Ayllón García (dueño del núcleo/orquestador):

- [ ] Wiring end-to-end: orquestador + 4 capas reales + agregador.
- [ ] `adapters/github_action/` (§12) — necesita orquestador + reputación ya resueltos. **Pendiente de decidir:** el workflow de ejemplo hace `pip install watchgate` (asume publicación); para desarrollo usar `pip install .` desde el checkout hasta que exista publicación real.
  Test de seguridad obligatorio: grep sobre los logs de una ejecución simulada buscando el valor literal de `WATCHGATE_LLM_API_KEY` — falla si aparece.
- [x] `shortcircuit.py` (§11, opcional/objetivo ampliado). ✅ Verificado en `tests/unit/test_shortcircuit.py`.
- [x] `tests/cases/` — los 10 casos mínimos (§14). **Hecho por Línea 2, más allá del reparto original de abajo** (los 10 casos estaban repartidos entre las tres líneas; en vez de esperar a que cada quien construyera los suyos, Línea 2 construyó los 10 -- reutilizando el mismo generador de repos git de dos commits ya usado para el benchmark de RAG -- y de paso los amplió a **191 casos**: 120 diffs benignos reales (PRs ya fusionados de click/jinja/requests/httpx/pydantic/black/pytest/urllib3/tqdm/rich/werkzeug), 61 muestras maliciosas reales (dataset público `DataDog/malicious-software-packages-dataset`, vetadas a mano para descartar las que no traían el payload real), y los 10 canónicos, todos con `metadata.json`/`expected.json`. Runner real en `tests/integration/pipeline_runner.py` + `tests/integration/test_cases.py` (marcados `integration`, no corren en el `pytest -q` normal -- llaman a la API real de Gemini). Informe autogenerado: `docs/validation_report.md`. **Limitación conocida:** el runner solo pesa `reputation`+`semantic` (`_WEIGHTS` en `pipeline_runner.py`), de antes de que `deps_layer.py` se registrara -- falta añadirlo a los pesos para que el score final compute las 3 capas reales que ya existen.
  Resultado de la primera pasada completa: 172/191 (90%) -- 100% en los 120 casos benignos (cero falsos positivos, incluidos los "difíciles": CI, Dockerfiles, dependencias), pero solo 20% en el tramo "difícil" de maliciosos (payload real enterrado en un fichero de miles de líneas). Causa identificada, no es ruido: el truncado de `build_user_prompt` (`_semantic/prompting.py`) solo preserva contenido si `static_findings_paths` lo marca, y esa señal depende de `static_layer.py`, que sigue sin implementar -- cualquier diff grande es hoy invisible para la capa semántica, con o sin intención maliciosa. Detalle completo y csv de resultados en `docs/validation_report.md`/`docs/validation_report_raw.json`.

  Reparto original de los 10 casos mínimos (para referencia, ya no aplica -- los 10 están hechos):

  | Caso | Semáforo esperado | Propietario original |
  |---|---|---|
  | `benign_refactor` | verde | Pablo Ayllón García |
  | `benign_new_feature_with_new_dep` | verde/amarillo | Pablo Ayllón García |
  | `cve_known_vulnerable_dependency` | amarillo/rojo | Pablo Ayllón García |
  | `xz_utils_simulado` | amarillo/rojo | Pablo Ayllón García |
  | `malicious_eval_base64` | rojo | Pablo Jiménez Castro |
  | `malicious_curl_pipe_bash_in_dockerfile` | rojo | Pablo Jiménez Castro |
  | `typosquat_dependency` | rojo | Pablo Jiménez Castro |
  | `atomic_arch_simulado` | rojo | Javier Martín Jurado |
  | `prt_scan_simulado` | rojo | Javier Martín Jurado |
  | `false_positive_candidate` | amarillo | Javier Martín Jurado |

  **Hecho cuando:** `tests/integration/test_cases.py` pasa los 10 casos y `docs/validation_report.md` se genera automáticamente desde el test runner (no se escribe a mano).

---

## Resumen de dependencias cruzadas (las únicas que existen)

1. **Fase 0 → todo lo demás** (bloqueante, ~1 día, Pablo Ayllón García).
2. **`cost_control.py` (Línea 1, Ayllón) → `_semantic/layer.py` (Línea 2, Javier)** — mitigable empezando contra una interfaz *fake*.
3. **Fase 1 completa → Fase 2** (integración final, coordinada por Ayllón).

Fuera de estos tres puntos, ninguna persona necesita esperar a otra para avanzar en su línea.

---

## Nota de entorno (para replicar la Fase 0 en tu máquina)

El proyecto usa `poetry` de verdad (no un `pip install` a mano). Si tu sistema trae un Python más antiguo (macOS suele traer 3.9), instala primero 3.11:

```bash
brew install python@3.11 poetry
cd watch_gate
poetry env use /opt/homebrew/bin/python3.11   # solo la primera vez
poetry install                                 # crea .venv/ y resuelve poetry.lock
make lint
make test
```

`poetry.lock` está commiteado — todo el equipo instala exactamente las mismas versiones, así que si `make lint`/`make test` te falla en local con las versiones que trae `poetry install`, es un bug real, no un problema de tu entorno.

**Por qué `make test` usa `poetry run python -m pytest` y no `poetry run pytest` a secas:** en algunos entornos (detectado en macOS durante esta revisión), los ficheros que `pip`/`poetry` escriben en `.venv` — incluido el `.pth` del que depende la instalación editable de `watchgate` — se crean con el atributo `hidden` del filesystem, y las versiones recientes de Python endurecidas en seguridad **ignoran silenciosamente cualquier `.pth` marcado como hidden**. El síntoma es `ModuleNotFoundError: No module named 'watchgate'` al ejecutar el script `pytest` suelto, aunque `pip show watchgate` diga que está instalado. `python -m pytest` no depende de ese `.pth`: añade el directorio actual a `sys.path`, así que watchgate se resuelve igual. Si os encontráis el mismo `ModuleNotFoundError` con alguna otra herramienta instalada como script de consola (no solo pytest), aplicad el mismo patrón: `poetry run python -m <herramienta>` en vez de `poetry run <herramienta>`.

**Sobre el choque de versiones de `rich` que se apuntó aquí en la revisión anterior:** era un falso positivo, producido por instalar paquetes con `pip` suelto sin resolver el árbol de dependencias completo (`pip` no comprobaba lo que ya tenía instalado). Con `poetry install` real, el resolutor fija `semgrep` en una versión (1.172.0) cuya dependencia es `rich>=13.5.2` (no la fijación estricta `~=13.5.2` que parecía en la instalación suelta), y `import-linter` pide `rich>=14.2.0` — ambas conviven sin problema en `rich 15.0.0`. No hay ninguna acción pendiente aquí.

**Verificado en verde con el toolchain real bloqueado por `poetry.lock`** (`ruff 0.5.7`, `mypy 1.20.2`, `pytest 8.4.2`, `import-linter 2.13`): `make lint` (ruff check + ruff format --check + mypy --strict + lint-imports) y `make test` (14/14, 100% cobertura sobre lo implementado), ejecutados tal cual los usará el equipo — no solo con un venv improvisado.
