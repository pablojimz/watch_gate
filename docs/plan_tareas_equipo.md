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

### Línea 1 — Pablo Ayllón García (núcleo, orquestador, agregador)

- [ ] **`diffparser.py`** (§2) — `parse_diff(repo_path, base_sha, head_sha) -> NormalizedDiff`, sin red, usando `GitPython`.
  Casos límite a testear explícitamente: diff vacío (`base_sha == head_sha`), archivo renombrado sin cambio de contenido, archivo binario (`is_binary=True`), historial con merge commits (usar `first_parent=True` al iterar).
  **Hecho cuando:** test con repo git real generado en `tempfile.mkdtemp()` (2 commits) devuelve exactamente los ficheros y autores esperados.

- [ ] **`aggregator.py` + `comment_template.py`** (§10) — `aggregate()`, `_semaforo()`, plantilla Jinja2 del comentario.
  **Hecho cuando:** con el ejemplo exacto de la memoria (estática 20, deps 10, reputación 40, semántica 85; pesos 0.25/0.20/0.15/0.40) el resultado es `score == 47` y `semaforo == AMARILLO`. Este test de regresión no debe fallar nunca.

- [ ] **`orchestrator.py`** (§9) — `run_analysis()` con `ThreadPoolExecutor`, filtro únicamente por `weight > 0` (sin ningún otro `if` de qué capa ejecutar).
  **Hecho cuando:** test con 4 capas *fake* (una con latencia simulada de 2s) muestra tiempo total ~2s (paralelo), no ~8s (secuencial).

- [ ] **`cost_control.py`** (§8) — `CostController` (estimación de tokens, truncado, cache SQLite, presupuesto mensual). Esquema exacto: `semantic_cache(diff_hash, output_json, created_at)`, `token_usage(repo, month, tokens_used)`.
  **Hecho cuando:** con presupuesto agotado simulado, `SemanticLayer.analyze` devuelve `skipped=True` **sin** llamar al LLM (mock HTTP con `call_count == 0`).

### Línea 2 — Javier Martín Jurado (reputación y semántica)

- [ ] **`reputation_layer.py`** (§6) — tabla de puntuación por reglas (no ML), suma con tope 100, capa que **nunca** hace llamadas HTTP (toda la metadata llega resuelta del adaptador).
  Señales exactas: cuenta <30 días (+30), 0 contribuciones previas (+20), email no verificado (+25), repo firma habitualmente pero commit no firmado (+30), firmado con clave nunca vista (+40).
  **Hecho cuando:** metadata simulando Atomic Arch (cuenta de 2 días, 0 contribuciones, email no verificado) da `risk_score >= 75`.

- [ ] **`rag/indexer.py` + `rag/retriever.py` + corpus** (§7.4) — corpus en `.md` (`xz_utils.md`, `prt_scan.md`, `atomic_arch.md` + entradas resumidas de MITRE ATT&CK: T1195 Supply Chain Compromise, T1027 Obfuscated Files, T1548 Abuse Elevation Control — decisión propia si se amplía). Embeddings con `sentence-transformers` (`all-MiniLM-L6-v2`, CPU, sin API externa), persistidos en ChromaDB local (`.watchgate/rag_index`, colección `attack_patterns`).
  **Hecho cuando:** `watchgate rag reindex` genera la colección persistente; `retrieve_relevant_context(diff_summary, k=3)` devuelve 3 fragmentos con `case_name`.

- [ ] **`_semantic/prompting.py` + `_semantic/tools.py`** (§7.1–7.2) — prompt de sistema literal de la spec, few-shot cargado de `datasets/few_shot/*.json`, 3 tools (`lookup_package_registry`, `get_commit_history`, `fetch_referenced_file`) con `ToolCallBudget(max_calls=3)`.
  **Hecho cuando:** al agotar el presupuesto de tool calls, el sistema fuerza `"Responde ahora con el JSON final"` y el modelo no puede pedir una 4ª herramienta.

- [ ] **`_semantic/client.py` + `_semantic/layer.py`** (§7.3, §7.5) — `LLMClient` (ABC) + `AnthropicClient` (**decisión humana ya tomada:** Anthropic). Reintento único si el JSON no parsea; si falla dos veces, `skipped=True, skip_reason="LLM no devolvió JSON válido tras 2 intentos"`.
  **Hecho cuando:** con un `LLMClient` *fake* inyectado (sin llamar a ninguna API real), el flujo completo RAG → prompt → parseo → cache funciona con una respuesta simulada.

*Nota de secuencia:* `_semantic/layer.py` llama a `cost_control` (Línea 1). Empezar contra una interfaz mínima/*fake* de `CostController` para no esperar a que Pablo Ayllón termine la implementación real; se integra al final de la fase.

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
- [ ] `shortcircuit.py` (§11, opcional/objetivo ampliado).
- [ ] `tests/cases/` — los 10 casos mínimos (§14), repartidos por quién posee la capa que cada caso ejerce principalmente:

  | Caso | Semáforo esperado | Propietario |
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
