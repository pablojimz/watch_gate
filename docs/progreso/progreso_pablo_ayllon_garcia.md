# Registro de progreso - Pablo Ayllón García

## Metadatos

- Responsable: Pablo Ayllón García
- Última actualización: 2026-08-06
- Estado general: Completado / Estable
- Última revisión realizada por: Pablo Ayllón García (Ingeniero Senior de Arquitectura)
- Componentes registrados: CLI (`watchgate/cli.py`), shortcircuit (`watchgate/core/shortcircuit.py`), deps_layers (`watchgate/core/layers/deps_layer.py`), Núcleo y Contratos de Fase 0 (`watchgate/core/models.py`, `watchgate/core/layers/base.py`, `watchgate/core/diffparser.py`, `watchgate/core/orchestrator.py`, `watchgate/core/aggregator.py`, `watchgate/core/comment_template.py`, `watchgate/core/cost_control.py`, `watchgate/config.py`).

---

# 1. Resumen general

El estado actual del trabajo asociado a la Línea 1 (Núcleo, Orquestador, Agregador, CLI y Cortocircuito) asignada a Pablo Ayllón García, junto con la capa de dependencias (`deps_layer.py`), presenta un grado de completitud y madurez técnica muy elevado.

La Fase 0 (Contrato compartido de datos y sistema de registro de capas de análisis) se encuentra totalmente cerrada y verificada mediante análisis estático y pruebas unitarias con tipado estricto. La arquitectura agnóstica garantiza el desacoplamiento entre el análisis Git en local, la orquestación concurrente multihilo, la agregación ponderada de puntuaciones de riesgo y la CLI de consola.

Asimismo, se han integrado componentes avanzados como el control de costes por tokens con caché SQLite (`cost_control.py`), la evaluación determinista de cortocircuito extremo previo a la invocación de LLMs (`shortcircuit.py`) y la capa de análisis de dependencias (`deps_layer.py`), que incluye detección de *typosquatting* vía algoritmos de distancia Levenshtein (`rapidfuzz`), análisis de vulnerabilidades conocidas mediante consultas batch a la API de OSV.dev con persistencia local, e inspección de scripts de instalación sospechosos.

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

### Estado actual

- **Funcionalidades implementadas**:
  - Subcomando `watchgate analyze`: Parsea argumentos Git (`--base`, `--head`, `--repo-path`), configuración (`--config`), metadatos de PR (`--pr-id`, `--repo`, `--author-login`), formato de salida (`--format comment|json`) y ruta de guardado (`--output`).
  - Subcomando `watchgate rag reindex`: Invocación de reindexado del corpus vectorial ChromaDB mediante `--index-path`.
  - Integración transparente de cortocircuito: si `config.shortcircuit_enabled` es True, ejecuta un análisis parcial de las capas ligeras (`static`, `deps`, `reputation`) y evalúa si se omite la capa semántica antes de instanciarla.
  - Soportado el manejo de presupuestos de tokens mediante `CostController` con liberación adecuada de recursos (`finally: cost_control.close()`).
  - Código de retorno dinámico: devuelve exit code `1` cuando `config.block_on_red` está activo y el semáforo global resulta `ROJO`.
- **Funcionalidades pendientes**:
  - Ninguna fundamental en el núcleo de la CLI. Integración futura con argumentos adicionales para el dashboard si se requiere.
- **Partes completas**: Parseo de flags, ejecución de orquestador, renderizado Markdown y JSON, exportación a fichero de salida y códigos de salida para pipelines de CI/CD.
- **Limitaciones conocidas**: Si el cliente LLM no puede instanciarse (por ejemplo, por falta de variable de entorno `ANTHROPIC_API_KEY` o `GEMINI_API_KEY`), la CLI captura la excepción silenciosamente y deja que `run_analysis` ejecute las capas restantes, marcando la semántica como omitida.

### Arquitectura e integración

- **Responsabilidad del componente**: Actuar como punto de entrada CLI y orquestador de nivel superior de la herramienta para ejecuciones locales o dentro de workflows de GitHub Actions / GitLab CI.
- **Módulos con los que interactúa**:
  - `watchgate.config`: Carga `.watchgate.yml` y variables de entorno.
  - `watchgate.core.diffparser`: Extracción de `NormalizedDiff`.
  - `watchgate.core.orchestrator`: Invocación de `run_analysis`.
  - `watchgate.core.cost_control`: Gestión del ciclo de vida de `CostController`.
  - `watchgate.core.shortcircuit`: Evaluación preliminar de cortocircuito.
  - `watchgate.core.comment_template`: Renderizado de plantilla Markdown.
  - `watchgate.core.rag.indexer`: Reconstrucción del índice de embeddings.
- **Dependencias**:
  - Internas: `watchgate.core.models`, `watchgate.core.layers._semantic`
  - Externas: `argparse`, `sys`, `pathlib`
- **Flujo de comunicación**: La CLI recibe parámetros por consola, los traduce a estructuras internas (`NormalizedDiff`, `WatchGateConfig`, dict de metadatos), ejecuta la evaluación parcial/total y emite los resultados formateados en la salida estándar o archivo.
- **Entradas y salidas**:
  - Entradas: Argumentos de línea de comandos (`sys.argv`).
  - Salidas: Salida estándar (`sys.stdout`) en formato Markdown o JSON; archivo en disco si se indica `--output`; entero de estado de proceso (`0` o `1`).

### Análisis técnico

- **Ficheros principales**: `watchgate/cli.py`
- **Clases importantes**:
  - `_ConfigWithoutSemantic`: Wrapper interno que filtra la clave `"semantic"` del diccionario de pesos para calcular la puntuación ponderada parcial durante el cortocircuito.
- **Funciones relevantes**:
  - `_build_parser() -> argparse.ArgumentParser`: Define la jerarquía de comandos y opciones.
  - `_cmd_analyze(args: argparse.Namespace) -> int`: Flujo de ejecución principal de análisis de PR.
  - `_cmd_rag_reindex(args: argparse.Namespace) -> int`: Ejecuta el reindexado del corpus vectorial.
  - `main(argv: list[str] | None = None) -> int`: Punto de entrada que procesa los argumentos y canaliza hacia el subcomando.
- **Flujo de ejecución**:
  1. Parseo de argumentos con `argparse`.
  2. Carga de configuración con `load_config()`.
  3. Extracción determinista del diff Git con `parse_diff()`.
  4. Si `shortcircuit_enabled=True`, se ejecuta `run_analysis()` con `_ConfigWithoutSemantic` y se evalúa `evaluate_shortcircuit()`.
  5. Si hay cortocircuito, se simula el resultado de la capa semántica con `skipped=True` y se calcula la agregación final. Si no, se instancia `CostController` y `SemanticLayer` mediante `layer_factories` y se ejecuta el análisis global.
  6. Formateo mediante `render_comment()` o `model_dump_json()`.
  7. Retorno de código de salida (`1` en semáforo ROJO con bloqueo activo; `0` en otro caso).
- **Flujo de datos**: `sys.argv` $\rightarrow$ `argparse.Namespace` $\rightarrow$ `NormalizedDiff` + `WatchGateConfig` $\rightarrow$ `AggregatedResult` $\rightarrow$ `str` (Markdown/JSON) $\rightarrow$ `stdout`/fichero.
- **Decisiones de diseño**:
  - Uso de la librería estándar `argparse` para evitar dependencias pesadas innecesarias como `Click` o `Typer` en el runtime básico de la CLI.
  - Inyección de `layer_factories` al orquestador para postergar la instanciación de `SemanticLayer` y sus recursos (conexión a DB, cliente HTTP) solo cuando realmente es requerida.

### Dependencias

#### Dependencias internas
- `watchgate.config`
- `watchgate.core.diffparser`
- `watchgate.core.orchestrator`
- `watchgate.core.aggregator`
- `watchgate.core.comment_template`
- `watchgate.core.cost_control`
- `watchgate.core.shortcircuit`
- `watchgate.core.models`
- `watchgate.core.rag.indexer`

#### Dependencias externas
- `argparse` (Librería estándar)
- `sys` (Librería estándar)
- `pathlib` (Librería estándar)

#### Interfaces utilizadas
- Protocolo `WatchGateConfig`
- `LayerFactory`

### Problemas detectados

- **Duplicación de código**: Ninguna observada.
- **Complejidad innecesaria**: Ninguna. El flujo lineal facilita la auditoría.
- **Problemas de diseño**: Ninguno crítico. Se gestiona de forma segura el ciclo de vida del controlador de costes (`CostController.close()`).
- **Falta de documentación**: Ninguna. La ayuda interactiva `--help` está totalmente parametrizada en español.
- **Riesgos de mantenimiento**: Mantener la coherencia de flags CLI si se añaden nuevos atributos a `WatchGateConfig`.
- **Dificultad de extensión**: Mínima; la arquitectura mediante subcomandos de `argparse` permite añadir nuevas opciones (p. ej. `watchgate dashboard launch`) con facilidad.

### Posibles mejoras

- **Refactorizaciones**: Ninguna prioritaria.
- **Mejoras arquitectónicas**: Posibilidad de soportar configuración por variables de entorno directamente desde la CLI.
- **Mejoras de rendimiento**: Ninguna requerida; el tiempo de arranque de la CLI es $< 0.1s$.
- **Mejoras de mantenibilidad**: Añadir autocompletado para bash/zsh si la CLI crece.
- **Mejoras de testing**: Incrementar los tests de integración probando comportamientos con repositorios remotos.
- **Cambios futuros**: Integración con adaptadores de CI adicionales.

### Estado para otros desarrolladores

- **Partes estables**: Toda la interfaz del comando `watchgate analyze` y `watchgate rag reindex`.
- **Partes a revisar antes de modificar**: La lógica de instanciación diferida de `SemanticLayer` a través de `layer_factories`.
- **Conocimientos necesarios**: Manejo de `argparse` y ciclo de vida de procesos Git/Python.
- **Tareas pendientes**: Ninguna pendiente en la CLI básica.

### Próximos pasos

1. Mantener sincronizados los argumentos de la CLI con los parámetros requeridos por la GitHub Action.

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
| 2026-08-06 | Pruebas de cobertura exhaustivas en `tests/unit/test_shortcircuit.py` | Verificación de casos límite y redondeos | Pablo Ayllón García |

### Estado actual

- **Funcionalidades implementadas**:
  - Evaluación matemática del score ponderado parcial sobre las capas activas (`static`, `deps`, `reputation`).
  - Cortocircuito a `Semaforo.ROJO`: Se activa cuando la nota parcial ponderada es tan elevada que, incluso en el caso hipotético de que la capa semántica puntuara `0`, el score global final resultante sería $\ge$ el umbral rojo (por defecto 70).
  - Cortocircuito a `Semaforo.VERDE`: Se activa cuando la nota parcial es extremadamente baja ($< \text{threshold\_yellow} \times 0.5$, típicamente $< 20$) y **no** se identifican patrones forzadores.
  - Patrones forzadores (`forces_semantic`): Se deshabilita el cortocircuito a VERDE si el diff toca archivos críticos (`PKGBUILD`, workflows de GitHub, `Makefile`, `Dockerfile`), incluye llamadas de red en el diff (`curl`, `requests`, `fetch`, etc.) o modifica manifiestos de dependencias (`package.json`, `requirements.txt`, etc.).
  - Muestreo aleatorio de auditoría (5%, $1/20$): Permite auditar periódicamente ejecuciones de bajo riesgo enviándolas a la capa semántica con soporte para *callbacks* de registro (`on_audit_sample`).
- **Funcionalidades pendientes**: Ninguna.
- **Partes completas**: Lógica de decisión, expresiones regulares de búsqueda, cálculo de promedios parciales y control de auditoría.
- **Limitaciones conocidas**: `_has_new_network_calls` utiliza heurísticas basadas en expresiones regulares sobre los *hunks* de diff, por lo que analiza líneas agregadas sin realizar análisis sintáctico profundo (tarea delegada a `static_layer.py`).

### Arquitectura e integración

- **Responsabilidad del componente**: Evaluar el resultado de las capas ligeras antes de llamar al modelo del lenguaje (LLM), evitando el consumo innecesario de tokens cuando la decisión es inequívoca o cuando la muestra no amerita análisis profundo.
- **Módulos con los que interactúa**:
  - `watchgate.core.aggregator`: Utiliza `weighted_average` para calcular la puntuación parcial.
  - `watchgate.core.layers._shared`: Consume `DEPENDENCY_MANIFEST_FILENAMES`.
  - `watchgate.core.models`: Consume `NormalizedDiff`, `LayerResult` y `Semaforo`.
- **Dependencias**:
  - Internas: `watchgate.core.aggregator`, `watchgate.core.layers._shared`, `watchgate.core.models`
  - Externas: `random`, `re`, `collections.abc`
- **Flujo de comunicación**: Es invocado por la CLI o adaptadores antes de la fase semántica. Recibe los resultados parciales de las capas ejecutadas y devuelve `Semaforo.ROJO`, `Semaforo.VERDE` o `None` (indicando que se debe proceder con la capa semántica).
- **Entradas y salidas**:
  - Entradas: `partial_results: dict[str, LayerResult]`, `weights: dict[str, float]`, `diff: NormalizedDiff`, `thresholds: dict[str, int]`, `rng`, `on_audit_sample`.
  - Salidas: `Semaforo | None`.

### Análisis técnico

- **Ficheros principales**: `watchgate/core/shortcircuit.py`
- **Clases importantes**: No aplica (módulo funcional).
- **Funciones relevantes**:
  - `_matches_forcing_pattern(diff: NormalizedDiff) -> bool`: Comprueba si la ruta de algún fichero modificado encaja con `FORCING_PATTERNS`.
  - `_has_new_network_calls(diff: NormalizedDiff) -> bool`: Escanea los parches de código no binarios en búsqueda de llamadas HTTP/red.
  - `_has_new_dependencies(diff: NormalizedDiff) -> bool`: Detecta si hay manifiestos de dependencias en el diff.
  - `evaluate_shortcircuit(...) -> Semaforo | None`: Función principal de decisión.
- **Flujo de ejecución**:
  1. Filtra los resultados parciales activos.
  2. Calcula el mínimo score global posible proyectando la capa semántica a 0.
  3. Si la proyección alcanza el umbral rojo, devuelve `Semaforo.ROJO`.
  4. Si no, verifica si existen patrones forzadores.
  5. Si no hay patrones forzadores y la señal parcial es inferior a la mitad del umbral amarillo:
     - Evalúa la probabilidad $1/20$ con `rng()`.
     - Si la probabilidad se cumple, ejecuta `on_audit_sample()` y devuelve `None`.
     - De lo contrario, devuelve `Semaforo.VERDE`.
  6. Si ninguna condición se cumple, devuelve `None`.
- **Flujo de datos**: `dict[str, LayerResult]` + `NormalizedDiff` $\rightarrow$ Cálculo matemático $\rightarrow$ `Semaforo | None`.
- **Decisiones de diseño**:
  - Para la decisión de cortocircuitar a ROJO, no se exige que la nota parcial sea $\ge 70$, sino que el cálculo `(suma_pesos_parciales * score_parcial) / peso_total_con_semantica` sea $\ge 70$. Esto previene falsos positivos en el cortocircuito si la capa semántica tiene un peso alto (ej. 0.40).

### Dependencias

#### Dependencias internas
- `watchgate.core.aggregator`
- `watchgate.core.layers._shared`
- `watchgate.core.models`

#### Dependencias externas
- `re` (Librería estándar)
- `random` (Librería estándar)
- `collections.abc` (Librería estándar)

#### Interfaces utilizadas
- `LayerResult`, `NormalizedDiff`, `Semaforo`

### Problemas detectados

- **Duplicación de código**: Ninguna.
- **Complejidad innecesaria**: Ninguna.
- **Problemas de diseño**: Ninguno. El diseño mediante funciones puras simplifica el testeo.
- **Falta de documentación**: Docstrings completos aclarando las decisiones de diseño.
- **Riesgos de mantenimiento**: Mínimos.
- **Dificultad de extensión**: Es sencillo añadir nuevos patrones a `FORCING_PATTERNS` o `_NETWORK_CALL_PATTERNS`.

### Posibles mejoras

- **Refactorizaciones**: Ninguna.
- **Mejoras arquitectónicas**: Permitir configurar los patrones forzadores desde `.watchgate.yml`.
- **Mejoras de rendimiento**: Precompilar expresiones regulares a nivel de módulo (ya implementado mediante `_FORCING_RE` y `_NETWORK_RE`).
- **Mejoras de testing**: Cubierto al 100%.
- **Cambios futuros**: Integrar persisistencias de muestras de auditoría en la BD del dashboard.

### Estado para otros desarrolladores

- **Partes estables**: Toda la función `evaluate_shortcircuit`.
- **Partes a revisar antes de modificar**: Lógica de cálculo de `min_possible_score`.
- **Conocimientos necesarios**: Ponderaciones matemáticas y expresiones regulares.
- **Tareas pendientes**: Ninguna.

### Próximos pasos

1. Monitorear el porcentaje de PRs cortocircuitadas en ejecuciones reales.

---

## 2.3 deps_layers

### Información básica

- Responsable: Asignado originalmente a Pablo Jiménez Castro (Línea 3); documentado e inspeccionado en este registro según el alcance de la tarea.
- Ubicación en el proyecto: `watchgate/core/layers/deps_layer.py`
- Estado actual: Completado y Operativo
- Última revisión: 2026-08-06
- Nivel de madurez: Producción / Estable

### Historial de cambios

| Fecha | Cambio realizado | Motivo | Responsable |
|------|------------------|--------|-------------|
| 2026-08-02 | Creación de parsers para `package.json`, `requirements.txt`, `PKGBUILD` y `Cargo.toml` | Extraer modificaciones de dependencias en múltiples ecosistemas (§5) | Equipo WatchGate |
| 2026-08-03 | Implementación de `TyposquatChecker` con `rapidfuzz` y normalización de separadores | Identificar ataques de typosquatting comparando contra listados de paquetes populares | Equipo WatchGate |
| 2026-08-04 | Integración de `OSVCache` con SQLite y soporte de consultas Batch POST a OSV.dev | Optimizar las consultas de vulnerabilidades reduciendo la latencia y respetando límites de red | Equipo WatchGate |
| 2026-08-05 | Inspección de scripts de instalación sospechosos (`postinstall`, etc.) mediante `analyze_install_script_text` | Detectar la inyección de comandos maliciosos en ganchos de instalación | Equipo WatchGate |
| 2026-08-06 | Verificación con tests unitarios e integración E2E (`test_deps_layer.py`, `test_cli_deps_integration.py`) | Confirmar el correcto funcionamiento de las alertas e inmunidad ante fallos de red | Equipo WatchGate |

### Estado actual

- **Funcionalidades implementadas**:
  - Parsers especializados de diffs para:
    - `package.json` (npm): Extrae dependencias directas, versiones URL/Git y ganchos de script (`preinstall`, `postinstall`, `install`).
    - `requirements.txt` / `Pipfile` (PyPI): Detecta paquetes, versiones fijadas/variables, instalaciones editables (`-e`) y URLs directas (`git+https`, `.whl`).
    - `PKGBUILD` (AUR): Identifica cambios en `depends` y `makedepends`.
    - `Cargo.toml` (Rust/crates.io): Parsea dependencias simples y tablas en línea con soporte para rutas Git o locales.
  - Comprobación de *Typosquatting*:
    - Utiliza `rapidfuzz.distance.Levenshtein` con una distancia $0 < d \le 2$ contra conjuntos de paquetes populares guardados en `datasets/typosquat_reference/` (`npm.txt`, `pypi.txt`, `aur.txt`, `crates.txt`).
    - Normalización inteligente de caracteres especiales (`_` reemplazado por `-`).
  - Consultas de vulnerabilidades conocidas en OSV.dev:
    - Peticiones eficientes por lotes (`https://api.osv.dev/v1/querybatch`) acotadas por un máximo de consultas por análisis (por defecto 20).
    - Mapeo de severidad precisa (`_is_high_or_critical_vuln`): Asigna score 90 si la vulnerabilidad es CRÍTICA o ALTA (CVSS $\ge 7.0$ o metadatos de base de datos) y 60 en vulnerabilidades menores.
    - Caché SQLite en disco (`OSVCache`, TTL 24 horas) con conmutación por error a `/tmp/.watchgate/cache.db` o `:memory:` si existen problemas de permisos en la carpeta del usuario.
  - Detección de scripts de instalación sospechosos: Asigna score $\ge 80$ si los scripts del paquete contienen patrones peligrosos (`curl | sh`, `eval`, `base64`, `chmod +x`, etc.).
  - Detección de dependencias directas desde URL/Git: Asigna score $\ge 75$.
  - Manejo degradado ante fallos de red: Un error de conexión a OSV **no** eleva el score a valores críticos, sino que asigna el valor base de nueva dependencia ($10$) e incluye la nota "No verificable por fallo de red en OSV".
- **Funcionalidades pendientes**: Ninguna en el alcance básico de la capa.
- **Partes completas**: Parsers de 4 ecosistemas, algoritmo de typosquatting, motor de caché con TTL, evaluador de vulnerabilidades OSV y reporte de justificación.
- **Limitaciones conocidas**: Los parsers de manifiestos operan sobre los parches de diff (`diff_hunk`), por lo que si una línea de dependencia se edita con formatos multilinea no estándar en JSON/TOML, el parser regex podría omitirla (comportamiento esperado frente a la sobrecostosa construcción de un AST completo de cada lenguaje).

### Arquitectura e integración

- **Responsabilidad del componente**: Analizar las dependencias añadidas o modificadas en la Pull Request para detectar vulnerabilidades de seguridad conocidas, nombres maliciosos y scripts de compilación/instalación sospechosos.
- **Módulos con los que interactúa**:
  - `watchgate.core.layers.base`: Extiende `AnalysisLayer` y se registra mediante `@register_layer`.
  - `watchgate.core.layers._shared`: Consume `DEPENDENCY_MANIFEST_FILENAMES` y `analyze_install_script_text`.
  - `watchgate.core.models`: Recibe `NormalizedDiff` y retorna `LayerResult`.
- **Dependencias**:
  - Internas: `watchgate.core.layers.base`, `watchgate.core.layers._shared`, `watchgate.core.models`
  - Externas: `httpx`, `pydantic`, `rapidfuzz`, `sqlite3`, `json`, `re`, `pathlib`, `threading`, `datetime`
- **Flujo de comunicación**: El orquestador ejecuta `DepsLayer.analyze()`. La capa filtra si existen manifiestos tocados, parsea las dependencias nuevas/modificadas, consulta la caché u OSV.dev, evalúa el typosquatting y genera el `LayerResult` con el score máximo hallado y las justificaciones detalladas.
- **Entradas y salidas**:
  - Entradas: `diff: NormalizedDiff`, `metadata: dict[str, Any]`.
  - Salidas: `LayerResult(layer_name="dependencies", risk_score=..., justification=...)`.

### Análisis técnico

- **Ficheros principales**: `watchgate/core/layers/deps_layer.py`
- **Clases importantes**:
  - `DependencyChange(BaseModel)`: Estructura de datos para representar una dependencia modificada.
  - `OSVCache`: Conexión multihilo a la base de datos SQLite de caché de vulnerabilidades con expiación TTL.
  - `TyposquatChecker`: Encargada de cargar los ficheros de referencia y ejecutar la distancia Levenshtein.
  - `DepsLayer(AnalysisLayer)`: Capa principal registrada en el sistema.
- **Funciones relevantes**:
  - `parse_package_json()`, `parse_requirements_txt()`, `parse_pkgbuild()`, `parse_cargo_toml()`: Parsers por ecosistema.
  - `_is_high_or_critical_vuln(vuln: dict) -> bool`: Clasificador de severidad CVSS/OSV.
  - `_query_osv_batch()`: Consulta combinada por lote a la API de OSV.
- **Flujo de ejecución**:
  1. Identifica si el diff contiene archivos manifiesto conocidos.
  2. Parsea los cambios para extraer los objetos `DependencyChange`.
  3. Ejecuta `_query_osv_batch()` aprovechando la caché local `OSVCache`.
  4. Para cada dependencia cambiada:
     - Comprueba typosquatting con `TyposquatChecker`.
     - Inspecciona scripts de instalación si existen.
     - Verifica si es una instalación desde URL/Git.
     - Analiza las vulnerabilidades retornadas por OSV.
  5. Asigna el score individual como el máximo de las alertas detectadas.
  6. Agrega los scores (`max(scores)`) y concatena las justificaciones.
- **Flujo de datos**: `NormalizedDiff` $\rightarrow$ `list[DependencyChange]` $\rightarrow$ Cache SQLite / OSV.dev API $\rightarrow$ `LayerResult`.
- **Decisiones de diseño**:
  - El score final de la capa de dependencias es el **máximo** (`max()`) de las puntuaciones individuales de las dependencias analizadas, en lugar de una suma. Esto evita que añadir 10 dependencias totalmente legítimas e inofensivas infle artificialmente el nivel de riesgo de la PR.

### Dependencias

#### Dependencias internas
- `watchgate.core.layers.base`
- `watchgate.core.layers._shared`
- `watchgate.core.models`

#### Dependencias externas
- `httpx`
- `pydantic`
- `rapidfuzz`
- `sqlite3`

#### Interfaces utilizadas
- `AnalysisLayer`

### Problemas detectados

- **Duplicación de código**: Los patrones de inspección de scripts se comparten adecuadamente con `_shared.py`.
- **Complejidad innecesaria**: Ninguna.
- **Problemas de diseño**: Ninguno. El uso de peticiones batch reduce significativamente la latencia.
- **Falta de documentación**: Los métodos clave contienen comentarios explicativos.
- **Riesgos de mantenimiento**: Si las estructuras de la API de OSV.dev sufren cambios breaking changes, `_is_high_or_critical_vuln` debe actualizarse.
- **Dificultad de extensión**: Mínima; añadir un nuevo ecosistema (ej. Go modules `go.mod`) solo requiere escribir una función `parse_go_mod()` y añadir un archivo de paquetes populares en `datasets/typosquat_reference/`.

### Posibles mejoras

- **Refactorizaciones**: Ninguna requerida actualmente.
- **Mejoras arquitectónicas**: Soporte para gestores de paquetes adicionales (Go, Composer).
- **Mejoras de rendimiento**: Pre-cargar en memoria los sets de typosquatting al arrancar la aplicación.
- **Mejoras de testing**: Mantener actualizados los mocks de respuesta de OSV.
- **Cambios futuros**: Actualización automatizada periódica de las listas de paquetes populares.

### Estado para otros desarrolladores

- **Partes estables**: La interfaz de la capa `DepsLayer`, el esquema SQLite y la integración con OSV.dev.
- **Partes a revisar antes de modificar**: Las expresiones regulares de los parsers de manifiestos.
- **Conocimientos necesarios**: Formatos de manifiestos de dependencias, API de OSV.dev y métricas de similitud de cadenas.
- **Tareas pendientes**: Ninguna pendiente.

### Próximos pasos

1. Monitorear el rendimiento de la caché SQLite en entornos de CI con contenedores efímeros.

---

## 2.4 Otros componentes relacionados detectados

Esta sección documenta los módulos del **Núcleo y la Fase 0** (responsabilidad de Pablo Ayllón García), esenciales para entender cómo se integran la CLI, `shortcircuit` y `deps_layer`.

### Componentes del Núcleo:

1. **`watchgate/core/models.py` (Contrato Compartido)**:
   - **Responsabilidad**: Define todas las entidades Pydantic del sistema: `FileChange`, `NormalizedDiff`, `CommitAuthor`, `LayerResult`, `AggregatedResult`, `ReputationMetadata`, y los enums `RiskCategory`, `Confidence`, `Semaforo`.
   - **Madurez**: Estable / Producción. Proporciona el contrato unificado JSON para el comentario de PR y el dashboard.

2. **`watchgate/core/layers/base.py` (Interfaz Base y Registro)**:
   - **Responsabilidad**: Proporciona la clase abstracta `AnalysisLayer`, el registro dinámico `LAYER_REGISTRY`, el decorador `@register_layer` y la función de envoltorio seguro `safe_analyze()`.
   - **Garantía de aislamiento**: `safe_analyze` asegura que ninguna excepción imprevista lanzada por una capa interrumpa el análisis global, traduciendo cualquier fallo en `LayerResult(skipped=True, skip_reason=...)`.

3. **`watchgate/core/diffparser.py` (Parser Git local)**:
   - **Responsabilidad**: Convierte un rango de commits `(repo_path, base_sha, head_sha)` en un objeto `NormalizedDiff` mediante GitPython local, de forma determinista y sin llamadas de red.
   - **Casos límite cubiertos**: Diff vacío (`base_sha == head_sha`), archivos binarios (`is_binary=True`), renombres y merges con `first_parent=True`.

4. **`watchgate/core/orchestrator.py` (Orquestador multihilo)**:
   - **Responsabilidad**: Ejecuta en paralelo con `ThreadPoolExecutor` todas las capas que poseen un peso $> 0$ en la configuración.
   - **Regla de diseño estricta**: No contiene ningún `if` condicional para seleccionar capas por nombre. Soporta `layer_factories` para instanciar capas con dependencias complejas.

5. **`watchgate/core/aggregator.py` & `comment_template.py` (Agregación y Renderizado)**:
   - **Responsabilidad**: `aggregate()` calcula el score ponderado redondeado y determina el semáforo (`VERDE` $<40$, `AMARILLO` $\ge 40$, `ROJO` $\ge 70$). `render_comment()` utiliza Jinja2 para producir el mensaje final en Markdown para el PR.

6. **`watchgate/core/cost_control.py` (Control de Coste de Tokens)**:
   - **Responsabilidad**: Estima consumo de tokens (~4 caracteres/token), trunca diffs masivos dando prioridad a ficheros con hallazgos estáticos/dependencias, gestiona la caché de respuestas semánticas en SQLite (`semantic_cache`) y mantiene el presupuesto de tokens mensual por repositorio (`token_usage`).

7. **`watchgate/config.py` (Gestión de Configuración)**:
   - **Responsabilidad**: Carga `.watchgate.yml` y variables de entorno (`WATCHGATE_`) con Pydantic Settings, aplicando validación de esquema y fallando rápido ante errores de sintaxis.

---

# 3. Relaciones entre componentes

La arquitectura de WatchGate está diseñada con un desacoplamiento estricto entre el punto de entrada, la extracción de datos de Git, la orquestación concurrente y la agregación de resultados.

## Flujo General de Ejecución

1. **Invocación**: La CLI (`cli.py`) recibe la llamada del usuario o del pipeline de CI/CD.
2. **Carga de Configuración**: `config.py` lee los pesos, umbrales y límites de presupuesto.
3. **Parseo de Diff**: `diffparser.py` lee el repositorio local Git y genera el `NormalizedDiff`.
4. **Evaluación de Cortocircuito (Opcional)**:
   - Si `shortcircuit_enabled` es verdadero, `orchestrator.py` ejecuta primero las capas ligeras (`static`, `deps`, `reputation`).
   - `shortcircuit.py` evalúa si el veredicto es concluyente (`ROJO` o `VERDE` sin patrones forzadores).
   - Si se cortocircuita, la capa semántica se marca como `skipped` y se pasa a la agregación.
5. **Análisis Multihilo**:
   - Si no hay cortocircuito, `orchestrator.py` instancia e invoca todas las capas activas en paralelo mediante `ThreadPoolExecutor`.
   - `DepsLayer` analiza los manifiestos, consulta la caché SQLite / API de OSV.dev y evalúa typosquatting.
   - `SemanticLayer` (si está activa) consulta `CostController` para verificar el presupuesto de tokens, recuperar caché o solicitar análisis al LLM con RAG.
6. **Agregación y Salida**:
   - `aggregator.py` calcula la puntuación final ponderada y el semáforo.
   - `comment_template.py` renderiza el comentario Markdown (o se genera el JSON equivalente).
   - La CLI imprime el resultado y retorna el código de salida correspondiente.

## Diagrama de Arquitectura e Integración (Mermaid)

```mermaid
graph TD
    User([Usuario / CI Pipeline]) -->|watchgate analyze| CLI[cli.py / _cmd_analyze]
    
    CLI --> Config[config.py / load_config]
    CLI --> DiffParser[diffparser.py / parse_diff]
    
    DiffParser -->|NormalizedDiff| CLI
    
    subgraph Control de Cortocircuito
        CLI -->|shortcircuit_enabled=True| PartialOrchestrator[orchestrator.py / run_analysis - Capas Parciales]
        PartialOrchestrator --> ShortCircuit[shortcircuit.py / evaluate_shortcircuit]
    end

    ShortCircuit -->|Verdict ROJO/VERDE| AggregatorShort[aggregator.py / aggregate]

    ShortCircuit -->|None / Proceed| FullOrchestrator[orchestrator.py / run_analysis - Todas las Capas]
    CLI -->|shortcircuit_enabled=False| FullOrchestrator

    subgraph Capas de Análisis Paralelas (ThreadPoolExecutor)
        FullOrchestrator -->|safe_analyze| StaticLayer[static_layer.py / StaticLayer]
        FullOrchestrator -->|safe_analyze| DepsLayer[deps_layer.py / DepsLayer]
        FullOrchestrator -->|safe_analyze| RepLayer[reputation_layer.py / ReputationLayer]
        FullOrchestrator -->|safe_analyze| SemLayer[_semantic/layer.py / SemanticLayer]
    end

    DepsLayer --> OSVCache[(OSVCache SQLite)]
    DepsLayer --> Typosquat[TyposquatChecker / rapidfuzz]
    SemLayer --> CostCtrl[(CostController SQLite)]

    FullOrchestrator --> Aggregator[aggregator.py / aggregate]
    
    Aggregator -->|AggregatedResult| CommentTpl[comment_template.py / render_comment]
    AggregatorShort -->|AggregatedResult| CommentTpl
    
    CommentTpl -->|Markdown / JSON| User
```

---

# 4. Estado global

## Resumen Ejecutivo

El núcleo de WatchGate y los componentes bajo la responsabilidad de Pablo Ayllón García (junto con la capa de dependencias) se encuentran en un estado de **alta madurez y estabilidad técnica**. Toda la Fase 0 y la Fase 1 correspondientes a la Línea 1 han sido implementadas, probadas y documentadas adecuadamente.

## Clasificación de Componentes por Madurez

- **Componentes Maduros (Listos para Producción)**:
  - `watchgate/core/models.py`: Contrato de datos Pydantic.
  - `watchgate/core/layers/base.py`: Registro y envoltorio seguro de capas.
  - `watchgate/core/diffparser.py`: Extracción determinista de diffs Git.
  - `watchgate/core/orchestrator.py`: Orquestador multihilo.
  - `watchgate/core/aggregator.py`: Calculador de promedios y semáforos.
  - `watchgate/core/comment_template.py`: Plantilla Jinja2 de comentarios.
  - `watchgate/core/cost_control.py`: Control de tokens y caché SQLite.
  - `watchgate/core/shortcircuit.py`: Cortocircuito de extremo.
  - `watchgate/core/layers/deps_layer.py`: Capa de dependencias completa.
  - `watchgate/cli.py`: Interfaz de línea de comandos.

- **Componentes en Desarrollo / Integración Externa**:
  - `adapters/github_action/`: Adaptador de integración en GitHub Action (Fase 2 de integración final).
  - Dashboard de postura de seguridad (`dashboard/`): Backend y Frontend (Línea 3).

## Riesgos Principales

1. **Dependencia de conectividad a la API de OSV.dev**: Si OSV.dev experimenta latencias elevadas o caídas, la caché SQLite mitiga el impacto en paquetes conocidos, pero peticiones de paquetes nuevos podrían demorar hasta el timeout de 10 segundos.
2. **Cuello de botella en entornos efímeros de CI**: En entornos como GitHub Actions donde el sistema de archivos es efímero, la caché SQLite de OSV y de tokens se destruye entre ejecuciones salvo que se configure la acción oficial de caching de GitHub (`actions/cache`).

---

# 5. Mejoras propuestas

## Alta prioridad

1. **Persistencia y restauración de caché SQLite en CI/CD**: Documentar e implementar la preservación de los archivos de caché (`.watchgate/cache.db` y `.watchgate/cost.db`) mediante la configuración de caché del runner de CI.
2. **Sincronización total con la GitHub Action (`adapters/github_action/`)**: Asegurar que los parámetros exportados por la CLI sean consumidos sin fricción por la acción de GitHub.

## Media prioridad

1. **Ampliación de parsers de dependencias**: Añadir soporte para `go.mod` (Golang) y `composer.json` (PHP) en `deps_layer.py`.
2. **Configuración dinámica de patrones forzadores**: Permitir personalización de las expresiones regulares de `FORCING_PATTERNS` a través de `.watchgate.yml`.

## Baja prioridad

1. **Autocompletado de la CLI**: Proporcionar scripts de autocompletado para zsh/bash en el paquete de distribución.
2. **Exportación de métricas OpenTelemetry**: Exponer métricas de tiempo de ejecución por capa y consumo de presupuesto de tokens.

---

# 6. Pendientes

- [x] Implementación y verificación de Fase 0 (Contrato compartido y `base.py`).
- [x] Implementación y testeo de `diffparser.py`.
- [x] Implementación y testeo de `aggregator.py` y `comment_template.py`.
- [x] Implementación y testeo de `orchestrator.py`.
- [x] Implementación y testeo de `cost_control.py`.
- [x] Implementación y testeo de `cli.py`.
- [x] Implementación y testeo de `shortcircuit.py`.
- [x] Implementación y testeo de `deps_layer.py`.
- [ ] Finalizar la Fase 2 de Integración End-to-End con el adaptador de GitHub Action (`adapters/github_action/`).
- [ ] Ejecutar y validar la batería de los 10 casos de prueba de integración (`tests/cases/`).
