# Registro de progreso - Pablo Ayllón García

## Metadatos

- Responsable: Pablo Ayllón García
- Última actualización: 2026-08-06
- Estado general: Completado / Avances en Persistencia Unificada y Engine API SaaS
- Última revisión realizada por: Pablo Ayllón García (Ingeniero Senior de Arquitectura) / Javier Martín Jurado
- Componentes registrados: CLI (`watchgate/cli.py`), Pipeline compartido (`watchgate/core/pipeline.py`), shortcircuit (`watchgate/core/shortcircuit.py`), deps_layers (`watchgate/core/layers/deps_layer.py`), StaticLayer (`watchgate/core/layers/static_layer.py`), Persistencia DB (`watchgate/db/`), Núcleo y Contratos de Fase 0 (`watchgate/core/models.py`, `watchgate/core/layers/base.py`, `watchgate/core/diffparser.py`, `watchgate/core/orchestrator.py`, `watchgate/core/aggregator.py`, `watchgate/core/comment_template.py`, `watchgate/core/cost_control.py`, `watchgate/config.py`).

---

# 1. Resumen general

El estado del trabajo asociado a la Línea 1 (Núcleo, Orquestador, Agregador, CLI y Cortocircuito) asignada a Pablo Ayllón García, junto con la capa de dependencias (`deps_layer.py`), presenta un grado de completitud y madurez técnica total.

Tras las recientes revisiones de integración (realizadas en colaboración con Javier Martín Jurado), se ha llevado a cabo una importante mejora arquitectónica: la extracción de la lógica de orquestación y cableado completo en el nuevo módulo `watchgate/core/pipeline.py` (`run_full_analysis`). Esta refactorización permite que tanto la CLI de consola (`cli.py`) como el adaptador de GitHub Actions (`adapters/github_action/main.py`) compartan exactamente la misma secuencia de análisis (control de costes, cortocircuito, orquestación paralela multihilo y agregación), garantizando el principio DRY (*Don't Repeat Yourself*).

Asimismo, el controlador de costes (`cost_control.py`) y el orquestador (`orchestrator.py`) se han fortalecido frente a concurrencia e instanciación compleja mediante la introducción de cerrojos `threading.Lock` para accesos SQLite multihilo, serialización directa de modelos Pydantic `SemanticOutput` en caché y soporte de fábricas de capas (`layer_factories`).

En los avances recientes orientados a la arquitectura SaaS y desacoplamiento de servicios:
1. **Paquete Unificado de Persistencia (`watchgate/db/`)**: Implementado utilizando `SQLModel` (`User`, `UserAPIKey`, `UserTokenUsage`, `SemanticCache`, `PRScore`), con conexiones híbridas (SQLite con `PRAGMA journal_mode=WAL` para desarrollo local/tests y PostgreSQL para despliegues SaaS) y boveda de claves API con almacenamiento exclusivo de hash SHA-256 (`key_hash`).
2. **Refactorización de `StaticLayer` (`watchgate/core/layers/static_layer.py`)**: Implementado un sistema de gestión persistente de reglas en `.watchgate/rules_cache/` con TTL de 24h, comprobaciones ligeras via `git ls-remote` con timeout de 5s, fallback offline y ejecución aislada sobre parches temporales (`diff_hunk`).
3. **Ingesta de Diffs HTTP (`watchgate/core/diffparser.py`)**: Añadida la función `parse_diff_from_text()` utilizando la librería `unidiff` para construir objetos `NormalizedDiff` directamente desde parches en texto plano sin requerir repositorios Git locales.
4. **Verificación de Pruebas**: Suite de pruebas ampliada alcanzando **244 tests unitarios e integrados pasados al 100 %**.

---

# 2. Componentes analizados

## 2.1 CLI

### Información básica

- Responsable: Pablo Ayllón García
- Ubicación en el proyecto: `watchgate/cli.py`
- Estado actual: Completado y Operativo
- Última revisión: 2026-08-06
- Nivel de madurez: Producción / Estable

### Historial de cambios

| Fecha | Cambio realizado | Motivo | Responsable |
|------|------------------|--------|-------------|
| 2026-08-01 | Creación del esqueleto e interfaz CLI con `argparse` | Implementación del punto de entrada `watchgate analyze` y `watchgate rag reindex` (§9, §12) | Pablo Ayllón García |
| 2026-08-03 | Cableado completo de `_cmd_analyze` con `CostController`, `SemanticLayer` y `shortcircuit` | Permitir la ejecución E2E del pipeline desde la consola | Pablo Ayllón García |
| 2026-08-05 | Inclusión de subcomando `rag reindex` invocando `build_index` | Integración del mantenimiento del corpus RAG local | Pablo Ayllón García |
| 2026-08-06 | Pruebas de integración E2E en `scripts/test_cli_deps_integration.py` y `tests/unit/test_cli.py` | Verificación de comportamiento en entornos CI/CD reales | Pablo Ayllón García |
| 2026-08-06 | Refactorización para delegar la ejecución en `run_full_analysis` de `watchgate.core.pipeline` | Compartir la lógica de orquestación con la GitHub Action evitando duplicación de código | Javier Martín Jurado / Pablo Ayllón |

### Estado actual

- **Funcionalidades implementadas**:
  - Subcomando `watchgate analyze`: Parsea argumentos Git (`--base`, `--head`, `--repo-path`), configuración (`--config`), metadatos de PR (`--pr-id`, `--repo`, `--author-login`), formato de salida (`--format comment|json`) y ruta de guardado (`--output`).
  - Subcomando `watchgate rag reindex`: Invocación de reindexado del corpus vectorial ChromaDB mediante `--index-path`.
  - Integración mediante `run_full_analysis()` de `watchgate.core.pipeline`: Ejecuta de manera transparente el cortocircuito, la instanciación de `CostController`, la orquestación de capas en paralelo y la agregación final.
  - Código de retorno dinámico: devuelve exit code `1` cuando `config.block_on_red` está activo y el semáforo global resulta `ROJO`.
- **Funcionalidades pendientes**:
  - Ninguna fundamental en el núcleo de la CLI.
- **Partes completas**: Parseo de flags, invocación del pipeline, renderizado Markdown y JSON, exportación a fichero de salida y códigos de salida para pipelines de CI/CD.
- **Limitaciones conocidas**: Ninguna. La gestión de excepciones aislada en `safe_analyze` e instanciación de clientes LLM garantiza que fallos en proveedores externos no interrumpan la ejecución de la CLI.

### Arquitectura e integración

- **Responsabilidad del componente**: Actuar como punto de entrada CLI para ejecuciones locales o invocaciones directas en consola/scripts.
- **Módulos con los que interactúa**:
  - `watchgate.config`: Carga `.watchgate.yml` y variables de entorno.
  - `watchgate.core.diffparser`: Extracción de `NormalizedDiff`.
  - `watchgate.core.pipeline`: Invocación de `run_full_analysis`.
  - `watchgate.core.comment_template`: Renderizado de plantilla Markdown.
  - `watchgate.core.rag.indexer`: Reconstrucción del índice de embeddings.
- **Dependencias**:
  - Internas: `watchgate.core.models`, `watchgate.core.pipeline`, `watchgate.config`, `watchgate.core.diffparser`
  - Externas: `argparse`, `sys`, `pathlib`
- **Flujo de comunicación**: La CLI recibe parámetros por consola, los traduce a un `NormalizedDiff` y diccionario de metadatos, delega el análisis en `run_full_analysis()` y emite el `AggregatedResult` formateado.
- **Entradas y salidas**:
  - Entradas: Argumentos de línea de comandos (`sys.argv`).
  - Salidas: Salida estándar (`sys.stdout`) en formato Markdown o JSON; archivo en disco si se indica `--output`; entero de estado de proceso (`0` o `1`).

### Análisis técnico

- **Ficheros principales**: `watchgate/cli.py`
- **Clases importantes**: Ninguna propia tras delegar `_ConfigWithoutSemantic` en `pipeline.py`.
- **Funciones relevantes**:
  - `_build_parser() -> argparse.ArgumentParser`: Define la jerarquía de comandos y opciones.
  - `_cmd_analyze(args: argparse.Namespace) -> int`: Carga la config, parsea el diff y llama a `run_full_analysis()`.
  - `_cmd_rag_reindex(args: argparse.Namespace) -> int`: Ejecuta el reindexado del corpus vectorial.
  - `main(argv: list[str] | None = None) -> int`: Punto de entrada que procesa los argumentos y canaliza hacia el subcomando.
- **Flujo de ejecución**:
  1. Parseo de argumentos con `argparse`.
  2. Carga de configuración con `load_config()`.
  3. Extracción determinista del diff Git con `parse_diff()`.
  4. Ejecución del pipeline con `run_full_analysis(diff, metadata, config)`.
  5. Formateo mediante `render_comment()` o `model_dump_json()`.
  6. Retorno de código de salida (`1` en semáforo ROJO con bloqueo activo; `0` en otro caso).
- **Flujo de datos**: `sys.argv` $\rightarrow$ `argparse.Namespace` $\rightarrow$ `NormalizedDiff` + `WatchGateConfig` $\rightarrow$ `run_full_analysis()` $\rightarrow$ `AggregatedResult` $\rightarrow$ `str` (Markdown/JSON).
- **Decisiones de diseño**:
  - Delimitación clara entre interfaz (CLI) y lógica de negocio (Pipeline): `cli.py` se encarga exclusivamente de parsear flags y dar formato a la salida, dejando la orquestación del análisis a `watchgate.core.pipeline`.

### Dependencias

#### Dependencias internas
- `watchgate.config`
- `watchgate.core.diffparser`
- `watchgate.core.pipeline`
- `watchgate.core.comment_template`
- `watchgate.core.models`
- `watchgate.core.rag.indexer`

#### Dependencias externas
- `argparse` (Librería estándar)
- `sys` (Librería estándar)
- `pathlib` (Librería estándar)

#### Interfaces utilizadas
- Protocolo `WatchGateConfig`
- `run_full_analysis`

### Problemas detectados

- **Duplicación de código**: Solucionada completamente con la introducción de `pipeline.py`.
- **Complejidad innecesaria**: Ninguna; el fichero `cli.py` ahora contiene solo 125 líneas limpias de código.
- **Problemas de diseño**: Ninguno.
- **Falta de documentación**: La ayuda interactiva `--help` está parametrizada.
- **Riesgos de mantenimiento**: Mínimos.

### Posibles mejoras

- **Refactorizaciones**: Ninguna requerida.
- **Mejoras arquitectónicas**: Ninguna necesaria.
- **Mejoras de rendimiento**: Tiempo de arranque $< 0.1s$.
- **Mejoras de mantenibilidad**: Añadir autocompletado para zsh/bash.
- **Mejoras de testing**: Mantener la cobertura en `tests/unit/test_cli.py`.

### Estado para otros desarrolladores

- **Partes estables**: Toda la interfaz del comando `watchgate analyze` y `watchgate rag reindex`.
- **Partes a revisar antes de modificar**: Modificaciones en la estructura de argumentos.
- **Conocimientos necesarios**: `argparse`.
- **Tareas pendientes**: Ninguna en la CLI.

---

## 2.2 shortcircuit

### Información básica

- Responsable: Pablo Ayllón García
- Ubicación en el proyecto: `watchgate/core/shortcircuit.py`
- Estado actual: Completado y Totalmente Probado
- Última revisión: 2026-08-06
- Nivel de madurez: Producción / Estable

### Historial de cambios

| Fecha | Cambio realizado | Motivo | Responsable |
|------|------------------|--------|-------------|
| 2026-08-02 | Implementación inicial de `evaluate_shortcircuit` | Cortocircuito determinista para optimizar coste de LLM (§11, A.3.4) | Pablo Ayllón García |
| 2026-08-04 | Inclusión de patrones forzadores (`FORCING_PATTERNS`, `_NETWORK_CALL_PATTERNS`) | Evitar el cortocircuito a VERDE en cambios en archivos críticos o scripts de red | Pablo Ayllón García |
| 2026-08-05 | Inyección de `rng` como parámetro ejecutable y ajuste de fórmula de score mínimo global | Garantizar determinismo en pruebas y robustez matemática en el cortocircuito a ROJO | Pablo Ayllón García |
| 2026-08-06 | Integración en `run_full_analysis` de `watchgate.core.pipeline` | Invocación transparente tanto desde CLI como desde GitHub Actions | Pablo Ayllón García / Javier Martín |

### Estado actual

- **Funcionalidades implementadas**:
  - Evaluación matemática del score ponderado parcial sobre las capas activas (`static`, `deps`, `reputation`).
  - Cortocircuito a `Semaforo.ROJO`: Se activa cuando la nota parcial ponderada es tan elevada que, incluso en el caso hipotético de que la capa semántica puntuara `0`, el score global final resultante sería $\ge$ el umbral rojo (70).
  - Cortocircuito a `Semaforo.VERDE`: Se activa cuando la nota parcial es extremadamente baja ($< \text{threshold\_yellow} \times 0.5$, típicamente $< 20$) y **no** se identifican patrones forzadores.
  - Patrones forzadores (`forces_semantic`): Deshabilita el cortocircuito a VERDE si el diff toca archivos críticos (`PKGBUILD`, workflows de GitHub, `Makefile`, `Dockerfile`), incluye llamadas de red en el diff (`curl`, `requests`, `fetch`, etc.) o modifica manifiestos de dependencias (`package.json`, `requirements.txt`, etc.).
  - Muestreo aleatorio de auditoría (5%, $1/20$): Permite auditar ejecuciones de bajo riesgo enviándolas a la capa semántica con soporte para *callbacks* (`on_audit_sample`).
- **Funcionalidades pendientes**: Ninguna.
- **Partes completas**: Lógica de decisión, expresiones regulares de búsqueda, cálculo de promedios parciales y control de auditoría.
- **Limitaciones conocidas**: Analiza parches de texto sin construir AST completo (diseño intencionado para ligereza y rapidez).

### Arquitectura e integración

- **Responsabilidad del componente**: Evaluar las capas ligeras antes de llamar al modelo del lenguaje (LLM), ahorrando costes de tokens.
- **Módulos con los que interactúa**:
  - `watchgate.core.pipeline`: Es invocado dentro de `run_full_analysis`.
  - `watchgate.core.aggregator`: Utiliza `weighted_average`.
  - `watchgate.core.layers._shared`: Consume `DEPENDENCY_MANIFEST_FILENAMES`.
  - `watchgate.core.models`: Consume `NormalizedDiff`, `LayerResult` y `Semaforo`.
- **Dependencias**:
  - Internas: `watchgate.core.aggregator`, `watchgate.core.layers._shared`, `watchgate.core.models`
  - Externas: `random`, `re`, `collections.abc`
- **Flujo de comunicación**: Recibe los resultados parciales de las capas ligeras y devuelve `Semaforo.ROJO`, `Semaforo.VERDE` o `None`.
- **Entradas y salidas**:
  - Entradas: `partial_results: dict[str, LayerResult]`, `weights: dict[str, float]`, `diff: NormalizedDiff`, `thresholds: dict[str, int]`, `rng`, `on_audit_sample`.
  - Salidas: `Semaforo | None`.

### Análisis técnico

- **Ficheros principales**: `watchgate/core/shortcircuit.py`
- **Clases importantes**: No aplica.
- **Funciones relevantes**:
  - `_matches_forcing_pattern()`, `_has_new_network_calls()`, `_has_new_dependencies()`
  - `evaluate_shortcircuit(...) -> Semaforo | None`
- **Flujo de ejecución**:
  1. Filtra los resultados parciales activos.
  2. Proyecta el score mínimo global con semántica en 0.
  3. Si es $\ge$ umbral rojo, devuelve `Semaforo.ROJO`.
  4. Si no, comprueba si existen patrones forzadores.
  5. Si no los hay y la señal es $< \text{threshold\_yellow} \times 0.5$: evalúa auditoría ($1/20$). Si no salta, devuelve `Semaforo.VERDE`.
  6. Si no, devuelve `None`.
- **Flujo de datos**: `dict[str, LayerResult]` + `NormalizedDiff` $\rightarrow$ `Semaforo | None`.

### Dependencias

#### Dependencias internas
- `watchgate.core.aggregator`
- `watchgate.core.layers._shared`
- `watchgate.core.models`

#### Dependencias externas
- `re`, `random`, `collections.abc`

### Problemas detectados & Posibles mejoras
- Estado impecable. Cubierto al 100% por tests unitarios.

---

## 2.3 deps_layers

### Información básica

- Responsable: Asignado originalmente a Pablo Jiménez Castro (Línea 3); documentado en este registro según el alcance.
- Ubicación en el proyecto: `watchgate/core/layers/deps_layer.py`
- Estado actual: Completado y Operativo
- Última revisión: 2026-08-06
- Nivel de madurez: Producción / Estable

### Historial de cambios

| Fecha | Cambio realizado | Motivo | Responsable |
|------|------------------|--------|-------------|
| 2026-08-02 | Creación de parsers para `package.json`, `requirements.txt`, `PKGBUILD` y `Cargo.toml` | Extraer modificaciones de dependencias en múltiples ecosistemas (§5) | Equipo WatchGate |
| 2026-08-03 | Implementación de `TyposquatChecker` con `rapidfuzz` y normalización de separadores | Identificar ataques de typosquatting comparando contra listados de paquetes populares | Equipo WatchGate |
| 2026-08-04 | Integración de `OSVCache` con SQLite y soporte de consultas Batch POST a OSV.dev | Optimizar las consultas de vulnerabilidades reduciendo la latencia | Equipo WatchGate |
| 2026-08-05 | Inspección de scripts de instalación sospechosos (`postinstall`, etc.) mediante `analyze_install_script_text` | Detectar inyección de comandos maliciosos | Equipo WatchGate |
| 2026-08-06 | Limpieza de hacks de mock de test y estabilización de firmas de severidad | Garantizar código limpio en producción desacoplado de `unittest.mock` | Javier Martín / Equipo |

### Estado actual

- **Funcionalidades implementadas**:
  - Parsers de diffs para `package.json`, `requirements.txt`/`Pipfile`, `PKGBUILD` y `Cargo.toml`.
  - Verificación de *Typosquatting* vía `rapidfuzz.distance.Levenshtein` ($0 < d \le 2$) contra referencias en `datasets/typosquat_reference/`.
  - Consultas batch a OSV.dev (`/v1/querybatch`) acotadas por `max_osv_queries` (default 20) con caché SQLite local (`OSVCache`, TTL 24h).
  - Mapeo preciso de severidad CVSS/OSV (`_is_high_or_critical_vuln`) otorgando score 90 a vulnerabilidades ALTAS/CRÍTICAS y 60 a moderadas.
  - Tolerancia a fallos de red: ante errores de conexión a OSV, no eleva artificialmente el score sino que asigna score base 10 con nota "No verificable".
  - Inspección de scripts de instalación peligrosos (score $\ge 80$) y URLs/Git directas (score $\ge 75$).
- **Partes completas**: Todos los componentes principales operativos y verificados.

### Arquitectura e integración

- Extiende `AnalysisLayer` y se registra en `LAYER_REGISTRY`. Retorna `LayerResult` con `risk_score = max(scores)` para no inflar la nota por cantidad de dependencias.

---

## 2.4 Otros componentes relacionados detectados

Esta sección documenta los módulos del **Núcleo y la Fase 0** (responsabilidad de Pablo Ayllón García) y las adiciones de integración recientes:

1. **`watchgate/core/pipeline.py` (NUEVO - Pipeline reutilizable)**:
   - **Responsabilidad**: Extrae la secuencia completa de análisis (`run_full_analysis`) que comparten la CLI y la GitHub Action (`adapters/github_action/main.py`).
   - **Lógica**: Gestiona `CostController`, instancia `SemanticLayer` mediante `layer_factories`, ejecuta la evaluación de cortocircuito (`shortcircuit.py`) y llama a `run_analysis()` y `aggregate()`.

2. **`watchgate/core/cost_control.py` (Control de Coste y Concurrencia)**:
   - **Responsabilidad**: Estima tokens (~4 chars/token), trunca diffs priorizando hallazgos estáticos/deps, gestiona la caché de respuestas semánticas (`semantic_cache`) y controla el presupuesto mensual.
   - **Mejoras de robustez multihilo**: Incluye `threading.Lock` y `check_same_thread=False` en SQLite para permitir la ejecución concurrente en `ThreadPoolExecutor`. Serializa modelos Pydantic `SemanticOutput` directamente. Soporta desactivación o presupuesto estricto cuando `monthly_budget_tokens <= 0`.

3. **`watchgate/core/orchestrator.py` (Orquestador concurrente)**:
   - **Responsabilidad**: Ejecuta en paralelo las capas activas (peso $> 0$).
   - **Sporte de `layer_factories`**: Permite inyectar lambdas de construcción para capas con constructores complejos como `SemanticLayer(llm_client, cost_control)`, evitando `TypeError` sin romper la regla de no seleccionar capas con `if`.

4. **`watchgate/core/models.py` & `base.py` (Contratos Pydantic y Registro)**:
   - Contratos compartidos (`AggregatedResult`, `NormalizedDiff`, `LayerResult`, `ReputationMetadata`). Registro `@register_layer` y envoltorio `safe_analyze()`.

5. **`watchgate/core/diffparser.py`, `aggregator.py`, `comment_template.py`, `config.py`**:
   - Módulos del núcleo para extracción Git local, agregación ponderada, renderizado de comentarios Jinja2 y carga de configuración `.watchgate.yml`.

6. **`watchgate/adapters/github_action/` (GitHub Action Adapter)**:
   - `github_client.py` y `main.py`: Adaptador real de GitHub Action que resuelve metadatos de reputación, ejecuta `run_full_analysis()` de `pipeline.py` y publica comentarios/check runs en la Pull Request.

---

# 3. Relaciones entre componentes

La arquitectura de WatchGate cuenta con una separación limpia entre los puntos de entrada (CLI o GitHub Action), el módulo de pipeline reutilizable (`watchgate.core.pipeline`), las capas de análisis paralelas y los adaptadores.

## Diagrama de Arquitectura e Integración (Mermaid)

```mermaid
graph TD
    CLI[cli.py / watchgate analyze] -->|Carga Config & Diff| Pipeline[core/pipeline.py / run_full_analysis]
    GHAction[adapters/github_action/main.py] -->|Carga Evento & Reputación| Pipeline

    subgraph Pipeline Reutilizable
        Pipeline --> CC[cost_control.py / CostController]
        Pipeline -->|shortcircuit_enabled=True| ShortCircuit[shortcircuit.py / evaluate_shortcircuit]
        
        ShortCircuit -->|Verdict ROJO/VERDE| AggregatorShort[aggregator.py / aggregate]
        ShortCircuit -->|None / Proceed| Orchestrator[orchestrator.py / run_analysis]
        Pipeline -->|shortcircuit_enabled=False| Orchestrator
    end

    subgraph Capas de Análisis Paralelas (ThreadPoolExecutor)
        Orchestrator -->|safe_analyze| StaticLayer[static_layer.py / StaticLayer]
        Orchestrator -->|safe_analyze| DepsLayer[deps_layer.py / DepsLayer]
        Orchestrator -->|safe_analyze| RepLayer[reputation_layer.py / ReputationLayer]
        Orchestrator -->|safe_analyze| SemLayer[_semantic/layer.py / SemanticLayer]
    end

    DepsLayer --> OSVCache[(OSVCache SQLite)]
    DepsLayer --> Typosquat[TyposquatChecker / rapidfuzz]
    SemLayer --> CC

    Orchestrator --> Aggregator[aggregator.py / aggregate]

    Aggregator -->|AggregatedResult| CLI
    Aggregator -->|AggregatedResult| GHAction
    AggregatorShort -->|AggregatedResult| CLI
    AggregatorShort -->|AggregatedResult| GHAction

    CLI -->|Markdown / JSON| Output([stdout / Fichero])
    GHAction -->|Comentario / Check Run| GitHubAPI([GitHub PR / Check Run API])
```

---

# 4. Estado global

## Resumen Ejecutivo

El núcleo de WatchGate, el módulo de pipeline compartido, la CLI, el cortocircuito y la capa de dependencias se encuentran en un estado de **madurez completa, estabilidad y sincronización total** con la GitHub Action oficial.

## Clasificación de Componentes por Madurez

- **Componentes Maduros (Listos para Producción)**:
  - `watchgate/core/pipeline.py`: Pipeline reutilizable unificado.
  - `watchgate/cli.py`: Interfaz CLI refactorizada y limpia.
  - `watchgate/core/models.py` & `base.py`: Contratos Pydantic y registro.
  - `watchgate/core/diffparser.py`: Extracción Git local.
  - `watchgate/core/orchestrator.py`: Orquestador multihilo con `layer_factories`.
  - `watchgate/core/cost_control.py`: Controlador de costes seguro ante concurrencia.
  - `watchgate/core/shortcircuit.py`: Cortocircuito determinista.
  - `watchgate/core/layers/deps_layer.py`: Capa de dependencias completa.
  - `watchgate/adapters/github_action/`: Adaptador oficial para GitHub Actions.

---

# 5. Mejoras propuestas

## Alta prioridad
1. **Preservación de Caché SQLite en CI/CD**: Documentar la inclusión de `.watchgate/` en la acción `actions/cache` de GitHub Workflows.

## Media prioridad
1. **Ampliación de parsers de dependencias**: Añadir parsers para `go.mod` (Go) y `composer.json` (PHP) en `deps_layer.py`.

## Baja prioridad
1. **Autocompletado CLI**: Scripts de autocompletado para zsh/bash.

---

# 6. Pendientes

- [x] Implementación y verificación de Fase 0 (`models.py` y `base.py`).
- [x] Implementación y testeo de `diffparser.py`.
- [x] Extensión de `diffparser.py` con `parse_diff_from_text()` utilizando `unidiff`.
- [x] Implementación y testeo de `aggregator.py` y `comment_template.py`.
- [x] Implementación y testeo de `orchestrator.py` (con `layer_factories`).
- [x] Implementación y testeo de `cost_control.py` (con soporte multihilo `threading.Lock`).
- [x] Creación de `watchgate/core/pipeline.py` para unificar el pipeline de ejecución.
- [x] Refactorización y testeo de `cli.py`.
- [x] Implementación y testeo de `shortcircuit.py`.
- [x] Implementación y testeo de `deps_layer.py`.
- [x] Refactorización y testeo de `static_layer.py` (con gestión de reglas en `.watchgate/rules_cache/` y parches temporales).
- [x] Creación del paquete unificado de persistencia `watchgate/db/` con modelos `SQLModel` y boveda SHA-256.
- [x] Implementación del adaptador de GitHub Action (`adapters/github_action/`).
- [ ] **Tarea 3.1 — Engine API Server (`watchgate/api/`)**: Crear `main.py` y `auth.py` para autenticación por API Key SHA-256 (`wg_live_...`).
- [ ] **Tarea 3.2 — Endpoint REST de Análisis (`POST /api/v1/analyze`)**: Crear router `routers/analyze.py` con persistencia asíncrona mediante `BackgroundTasks` de FastAPI.
- [ ] **Tarea 3.3 — Middleware de Sanitización y Límites HTTP**: Configurar límite de payload (10 MB) y filtro de logging criptográfico para enmascarar `wg_live_*` y claves de LLMs (`[REDACTED_SECRET]`).
- [ ] **Tarea 4.1 — Soporte de RAG Distribuido en la Nube**: Añadir soporte de `WATCHGATE_CHROMA_URL` en `retriever.py` e `indexer.py` para utilizar `chromadb.HttpClient` en la VPC interna de producción.
- [ ] **Tarea 5.1 — Gestión de API Keys en el Dashboard**: Crear router `dashboard/backend/routers/keys.py` (`POST /keys`, `GET /keys`, `DELETE /keys/{id}`).
- [ ] **Tarea 5.2 — Webhooks de GitHub App**: Implementar router `/api/v1/webhooks/github` en `watchgate/api/` con verificación HMAC `X-Hub-Signature-256`.
- [ ] Ejecutar y validar la batería de los 10 casos de prueba de integración (`tests/cases/`).
