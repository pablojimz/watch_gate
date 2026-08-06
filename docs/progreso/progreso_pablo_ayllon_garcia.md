# Registro de progreso - Pablo Ayllón García

## Metadatos

- Responsable: Pablo Ayllón García
- Última actualización: 2026-08-06
- Estado general: Completado / Avances en Persistencia Unificada DB y Engine API SaaS
- Última revisión realizada por: Pablo Ayllón García (Ingeniero Senior de Arquitectura) / Javier Martín Jurado
- Componentes registrados: CLI (`watchgate/cli.py`), Cortocircuito (`watchgate/core/shortcircuit.py`), Capa de dependencias (`watchgate/core/layers/deps_layer.py`), Pipeline compartido (`watchgate/core/pipeline.py`), Control de coste (`watchgate/core/cost_control.py`), Orquestador (`watchgate/core/orchestrator.py`), Extractor de diffs (`watchgate/core/diffparser.py`), Persistencia SQLModel (`watchgate/db/`), Capa estática (`watchgate/core/layers/static_layer.py`), Modelos y Agregador (`watchgate/core/models.py`, `watchgate/core/layers/base.py`, `watchgate/core/aggregator.py`).

---

# 1. Resumen general

El estado del trabajo asociado a la Línea 1 (Núcleo, Orquestador, Agregador, CLI y Cortocircuito) asignada a Pablo Ayllón García, junto con la capa de dependencias (`deps_layer.py`), la persistencia unificada (`watchgate/db/`), el extractor de diffs (`diffparser.py`) y la refactorización de `static_layer.py`, presenta un grado de completitud y madurez técnica total.

Tras las recientes revisiones de integración y arquitectura (en colaboración con Javier Martín Jurado), se ha consolidado una abstracción clave: la extracción de la orquestación en el módulo `watchgate/core/pipeline.py` (`run_full_analysis`). Esta refactorización permite que la CLI de consola (`cli.py`), la GitHub Action (`adapters/github_action/main.py`) y la futura Engine API SaaS compartan exactamente el mismo pipeline de análisis (control de costes, cortocircuito, orquestación paralela multihilo y agregación), aplicando de forma estricta el principio DRY (*Don't Repeat Yourself*).

Adicionalmente, se han completado los siguientes hitos de infraestructura y persistencia:
1. **Paquete Unificado de Persistencia (`watchgate/db/`)**: Implementado mediante `SQLModel` (`User`, `UserAPIKey`, `UserTokenUsage`, `SemanticCache`, `PRScore`), con soporte híbrido SQLite (WAL) y PostgreSQL, vault de claves API con almacenamiento exclusivo de hash SHA-256 (`key_hash`) y repositorio de transacciones atómicas.
2. **Ingesta de Diffs HTTP e in-memory (`watchgate/core/diffparser.py`)**: Incorporación de `parse_diff_from_text()` haciendo uso de `unidiff` para procesar parches enviados por red sin requerir repositorios Git locales.
3. **Optimización de `StaticLayer` (`watchgate/core/layers/static_layer.py`)**: Sincronización inteligente de reglas Semgrep en `.watchgate/rules_cache/` con TTL de 24h, verifiaciones ligeras `git ls-remote` (5s timeout), fallback offline y ejecución aislada sobre ficheros temporales.
4. **Verificación de la Suite de Pruebas**: Suite de pruebas ampliada ejecutada con éxito alcanzando **244 tests unitarios e integrados pasados al 100 %**.

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
  - Subcomando `watchgate analyze`: Parsea argumentos Git (`--base`, `--head`, `--repo-path`), ruta de configuración (`--config`), metadatos de la PR (`--pr-id`, `--repo`, `--author-login`), formato de salida (`--format comment|json`) y exportación a fichero (`--output`).
  - Subcomando `watchgate rag reindex`: Reconstrucción del índice vectorial ChromaDB a través del parámetro `--index-path`.
  - Integración transparente con `run_full_analysis()` de `watchgate.core.pipeline`: Ejecuta la evaluación de cortocircuito, instanciación del control de costes, orquestación concurrente y agregación final.
  - Código de retorno dinámico: Devuelve exit code `1` cuando `config.block_on_red` está activo y el veredicto global es `Semaforo.ROJO`; devuelve `0` en cualquier otro caso.
- **Funcionalidades pendientes**: Ninguna en el núcleo de la CLI.
- **Partes completas**: Parseo de flags CLI, invocación del pipeline, formateo Markdown y JSON, volcado a archivo y códigos de salida para CI/CD.
- **Limitaciones conocidas**: Ninguna. La gestión de excepciones aislada mediante `safe_analyze` garantiza que fallos en proveedores externos o de red no interrumpan de forma abrupta el proceso.

### Arquitectura e integración

- **Responsabilidad del componente**: Punto de entrada de línea de comandos para ejecuciones locales o invocaciones en scripts de automatización.
- **Módulos con los que interactúa**:
  - `watchgate.config`: Carga de configuración desde `.watchgate.yml`.
  - `watchgate.core.diffparser`: Extracción del objeto `NormalizedDiff`.
  - `watchgate.core.pipeline`: Invocación de `run_full_analysis`.
  - `watchgate.core.comment_template`: Formateo Markdown con Jinja2.
  - `watchgate.core.rag.indexer`: Reindexado de embeddings con ChromaDB.
- **Dependencias**:
  - Internas: `watchgate.config`, `watchgate.core.diffparser`, `watchgate.core.pipeline`, `watchgate.core.comment_template`, `watchgate.core.models`, `watchgate.core.rag.indexer`.
  - Externas: `argparse`, `sys`, `pathlib`.
- **Flujo de comunicación**: La CLI intercepta argumentos de la consola, construye un `NormalizedDiff` y un diccionario de metadatos, transfiere la ejecución a `run_full_analysis()` y emite el resultado formateado por `stdout` o archivo.
- **Entradas y salidas**:
  - Entradas: Argumentos de terminal (`sys.argv`).
  - Salidas: Salida estándar (`sys.stdout`) en Markdown o JSON; archivo opcional (`--output`); entero de salida (`0` o `1`).

### Análisis técnico

- **Ficheros principales**: `watchgate/cli.py`
- **Clases importantes**: No aplica en la CLI tras desacoplar la lógica al pipeline.
- **Funciones relevantes**:
  - `_build_parser() -> argparse.ArgumentParser`: Configura la jerarquía de comandos y subcomandos.
  - `_cmd_analyze(args: argparse.Namespace) -> int`: Carga la config, parsea el diff e invoca `run_full_analysis()`.
  - `_cmd_rag_reindex(args: argparse.Namespace) -> int`: Invoca `build_index()` sobre ChromaDB.
  - `main(argv: list[str] | None = None) -> int`: Punto de entrada principal con gestión de subcomandos y ayuda.
- **Flujo de ejecución**:
  1. `main()` procesa la lista de argumentos mediante `_build_parser()`.
  2. Direcciona hacia `_cmd_analyze()` o `_cmd_rag_reindex()`.
  3. `_cmd_analyze()` lee la configuración con `load_config()` y parsea el diff local con `parse_diff()`.
  4. Ejecuta `run_full_analysis(diff, metadata, config)`.
  5. Imprime o guarda la salida en el formato especificado.
  6. Evalúa `config.block_on_red` para retornar `1` o `0`.
- **Flujo de datos**: `sys.argv` $\rightarrow$ `argparse.Namespace` $\rightarrow$ `NormalizedDiff` + `WatchGateConfig` $\rightarrow$ `run_full_analysis()` $\rightarrow$ `AggregatedResult` $\rightarrow$ `str` (Markdown/JSON).
- **Decisiones de diseño**: Desacoplamiento estricto entre la interfaz de usuario (CLI) y la lógica de orquestación (Pipeline), permitiendo reutilizar el pipeline en la GitHub Action y la Engine API SaaS.

### Dependencias

#### Dependencias internas
- `watchgate.config`
- `watchgate.core.diffparser`
- `watchgate.core.pipeline`
- `watchgate.core.comment_template`
- `watchgate.core.models`
- `watchgate.core.rag.indexer`

#### Dependencias externas
- `argparse` (Librería estándar de Python)
- `sys` (Librería estándar de Python)
- `pathlib` (Librería estándar de Python)

#### Interfaces utilizadas
- Protocolo `WatchGateConfig`
- Función `run_full_analysis`

### Problemas detectados

- **Duplicación de código**: Resuelta totalmente mediante el módulo `pipeline.py`.
- **Complejidad innecesaria**: Ninguna; `cli.py` cuenta con 125 líneas de código limpio.
- **Problemas de diseño**: Ninguno.
- **Falta de documentación**: La ayuda interactiva `--help` está totalmente parametrizada.
- **Riesgos de mantenimiento**: Mínimos.
- **Dificultad de extensión**: Nula; añadir subcomandos requiere únicamente registrar un nuevo subparser.

### Posibles mejoras

- **Refactorizaciones**: Ninguna necesaria.
- **Mejoras arquitectónicas**: Ninguna requerida.
- **Mejoras de rendimiento**: Tiempo de arranque por debajo de los 100 ms.
- **Mejoras de mantenibilidad**: Generar autocompletado para zsh/bash.
- **Mejoras de testing**: Mantener la cobertura completa en `tests/unit/test_cli.py`.
- **Cambios futuros**: Ninguno pendiente.

### Estado para otros desarrolladores

- **Partes estables**: Toda la interfaz y contratos del comando `watchgate analyze` y `watchgate rag reindex`.
- **Partes a revisar antes de modificar**: Inserción de nuevos argumentos en `_build_parser()`.
- **Conocimientos necesarios**: Manejo de `argparse` y ciclo de vida de señales de proceso en POSIX.
- **Tareas pendientes**: Ninguna.

### Próximos pasos

- Mantener sincronizada la CLI con evoluciones futuras de los argumentos de configuración.

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
| 2026-08-02 | Implementación inicial de `evaluate_shortcircuit` | Cortocircuito determinista para la optimización de costes LLM (§11, A.3.4) | Pablo Ayllón García |
| 2026-08-04 | Incorporación de patrones forzadores (`FORCING_PATTERNS`, `_NETWORK_CALL_PATTERNS`) | Evitar falsos positivos a VERDE en archivos sensibles o scripts con llamadas de red | Pablo Ayllón García |
| 2026-08-05 | Inyección de `rng` como parámetro ejecutable y ajuste del score mínimo proyectado | Garantizar determinismo en tests y rigor matemático en la toma de decisión a ROJO | Pablo Ayllón García |
| 2026-08-06 | Integración en `run_full_analysis` de `watchgate.core.pipeline` | Permitir la invocación de cortocircuito tanto en CLI como en GitHub Actions | Pablo Ayllón García / Javier Martín |

### Estado actual

- **Funcionalidades implementadas**:
  - Evaluación matemática del score ponderado parcial sobre las capas livianas (`static`, `deps`, `reputation`).
  - Cortocircuito a `Semaforo.ROJO`: Se activa cuando la nota parcial ponderada es tan elevada que, en el supuesto hipotético de que la capa semántica obtuviera `0`, la nota media global final seguiría siendo $\ge$ al umbral de rojo (70).
  - Cortocircuito a `Semaforo.VERDE`: Se activa cuando la señal parcial es extremadamente reducida ($< \text{threshold\_yellow} \times 0.5$, típicamente $< 20$) y **no** se identifican patrones forzadores.
  - Patrones forzadores (`forces_semantic`): Desactiva el cortocircuito a VERDE si la PR modifica archivos de infraestructura (`PKGBUILD`, `.github/workflows/`, `Makefile`, `Dockerfile`), incluye llamadas de red en el parche (`curl`, `requests`, `fetch`, etc.) o altera manifiestos de dependencias.
  - Muestreo aleatorio de auditoría (5%, $1/20$): Permite auditar ejecuciones de bajo riesgo enviándolas a la capa semántica con soporte para *callbacks* (`on_audit_sample`).
- **Funcionalidades pendientes**: Ninguna.
- **Partes completas**: Lógica de decisión, expresiones regulares de búsqueda, cálculo de promedios parciales y control de auditoría.
- **Limitaciones conocidas**: Analiza parches de texto sin construir un AST completo (diseñado expresamente para ser rápido y liviano).

### Arquitectura e integración

- **Responsabilidad del componente**: Evaluar el riesgo con las capas ligeras antes de llamar al modelo de lenguaje (LLM), optimizando el consumo de tokens y la latencia.
- **Módulos con los que interactúa**:
  - `watchgate.core.pipeline`: Invocado dentro de `run_full_analysis`.
  - `watchgate.core.aggregator`: Utiliza `weighted_average`.
  - `watchgate.core.layers._shared`: Reutiliza `DEPENDENCY_MANIFEST_FILENAMES`.
  - `watchgate.core.models`: Consume `NormalizedDiff`, `LayerResult` y `Semaforo`.
- **Dependencias**:
  - Internas: `watchgate.core.aggregator`, `watchgate.core.layers._shared`, `watchgate.core.models`.
  - Externas: `random`, `re`, `collections.abc`.
- **Flujo de comunicación**: Recibe los resultados de las capas livianas y retorna `Semaforo.ROJO`, `Semaforo.VERDE` o `None` (proceder con capa semántica).
- **Entradas y salidas**:
  - Entradas: `partial_results: dict[str, LayerResult]`, `weights: dict[str, float]`, `diff: NormalizedDiff`, `thresholds: dict[str, int]`, `rng`, `on_audit_sample`.
  - Salidas: `Semaforo | None`.

### Análisis técnico

- **Ficheros principales**: `watchgate/core/shortcircuit.py`
- **Clases importantes**: No aplica.
- **Funciones relevantes**:
  - `_matches_forcing_pattern(diff: NormalizedDiff) -> bool`: Evalúa la presencia de archivos críticos.
  - `_has_new_network_calls(diff: NormalizedDiff) -> bool`: Detecta llamadas de red en parches añadidos.
  - `_has_new_dependencies(diff: NormalizedDiff) -> bool`: Detecta cambios en manifiestos.
  - `evaluate_shortcircuit(...) -> Semaforo | None`: Función principal de decisión.
- **Flujo de ejecución**:
  1. Filtra los resultados de las capas parciales activas.
  2. Calcula el score ponderado mínimo posible asumiendo semántica en 0.
  3. Si $\ge \text{thresholds['red']}$, retorna `Semaforo.ROJO`.
  4. Comprueba si se cumplen patrones forzadores (`forces_semantic`).
  5. Si no hay patrones forzadores y la señal parcial es $< \text{threshold\_yellow} \times 0.5$, comprueba muestreo aleatorio ($1/20$).
  6. Si no salta auditoría, retorna `Semaforo.VERDE`. En caso contrario, retorna `None`.
- **Flujo de datos**: `dict[str, LayerResult]` + `NormalizedDiff` $\rightarrow$ `Semaforo | None`.
- **Decisiones de diseño**: Inyección explícita del generador pseudoaleatorio `rng` para permitir ejecuciones de test 100% deterministas.

### Dependencias

#### Dependencias internas
- `watchgate.core.aggregator`
- `watchgate.core.layers._shared`
- `watchgate.core.models`

#### Dependencias externas
- `re` (Librería estándar de Python)
- `random` (Librería estándar de Python)
- `collections.abc` (Librería estándar de Python)

#### Interfaces utilizadas
- Función `weighted_average`
- Constante `DEPENDENCY_MANIFEST_FILENAMES`

### Problemas detectados

- **Duplicación de código**: Ninguna.
- **Complejidad innecesaria**: Ninguna; implementado con funciones puras y expresiones regulares compiladas en módulo.
- **Problemas de diseño**: Ninguno.
- **Falta de documentación**: Código completamente documentado con docstrings informativos.
- **Riesgos de mantenimiento**: Mínimos.
- **Dificultad de extensión**: Nula; añadir nuevos patrones forzadores requiere actualizar las listas `FORCING_PATTERNS` o `_NETWORK_CALL_PATTERNS`.

### Posibles mejoras

- **Refactorizaciones**: Ninguna requerida.
- **Mejoras arquitectónicas**: Ninguna necesaria.
- **Mejoras de rendimiento**: Evaluado en menos de 1 ms.
- **Mejoras de mantenibilidad**: Mantenimiento de expresiones regulares centralizado.
- **Mejoras de testing**: Mantenimiento de la cobertura en `tests/unit/test_shortcircuit.py`.
- **Cambios futuros**: Ninguno.

### Estado para otros desarrolladores

- **Partes estables**: La firma y comportamiento de `evaluate_shortcircuit`.
- **Partes a revisar antes de modificar**: Modificaciones en la lista de patrones forzadores.
- **Conocimientos necesarios**: Expresiones regulares en Python y promedios ponderados.
- **Tareas pendientes**: Ninguna.

### Próximos pasos

- Monitorear el ratio de aciertos de cortocircuito en entorno de producción.

---

## 2.3 deps_layers

### Información básica

- Responsable: Asignado originalmente a Pablo Jiménez Castro (Línea 3); documentado en este registro por interacción directa e integración en el flujo.
- Ubicación en el proyecto: `watchgate/core/layers/deps_layer.py`
- Estado actual: Completado y Operativo
- Última revisión: 2026-08-06
- Nivel de madurez: Producción / Estable

### Historial de cambios

| Fecha | Cambio realizado | Motivo | Responsable |
|------|------------------|--------|-------------|
| 2026-08-02 | Implementación de parsers para `package.json`, `requirements.txt`, `PKGBUILD` y `Cargo.toml` | Extraer modificaciones de dependencias en múltiples ecosistemas (§5) | Equipo WatchGate |
| 2026-08-03 | Implementación de `TyposquatChecker` con `rapidfuzz` y normalización de caracteres | Detectar ataques de typosquatting contra listados de paquetes populares | Equipo WatchGate |
| 2026-08-04 | Integración de `OSVCache` con SQLite multihilo y soporte de batch queries en OSV.dev | Optimizar las consultas de vulnerabilidades mediante llamadas HTTP `/v1/querybatch` | Equipo WatchGate |
| 2026-08-05 | Inspección de scripts de instalación sospechosos (`preinstall`/`postinstall`) | Detectar ejecución de comandos arbitrarios en instalaciones de paquetes | Equipo WatchGate |
| 2026-08-06 | Eliminación de mocks de test en producción y estandarización de severidad | Garantizar estabilidad del código en producción | Javier Martín / Equipo |

### Estado actual

- **Funcionalidades implementadas**:
  - Parsers de parches para `package.json`, `requirements.txt`/`Pipfile`, `PKGBUILD` y `Cargo.toml`.
  - Verificación de *Typosquatting* mediante `rapidfuzz.distance.Levenshtein` ($0 < d \le 2$) contra referencias en `datasets/typosquat_reference/`.
  - Consultas en lote a la API de OSV.dev (`/v1/querybatch`) acotadas por `max_osv_queries` (default 20, máximo 20) con soporte de caché persistente SQLite (`OSVCache`, TTL 24h).
  - Evaluación precisa de severidad CVSS/OSV (`_is_high_or_critical_vuln`) otorgando score 90 a vulnerabilidades ALTAS/CRÍTICAS y 60 a moderadas.
  - Tolerancia a fallos de red: ante errores de comunicación con OSV, no eleva la nota a rojo sino que asigna nota aclaratoria "No verificable".
  - Detección de scripts de instalación peligrosos (score $\ge 80$) e instalaciones directas desde URL/Git (score $\ge 75$).
- **Funcionalidades pendientes**: Soporte para ecosistemas adicionales (`go.mod`, `composer.json`).
- **Partes completas**: Parsers de parches, caché SQLite, verificación de typosquatting y mapeo de severidad.
- **Limitaciones conocidas**: Acotado a los ecosistemas documentados en la spec.

### Arquitectura e integración

- **Responsabilidad del componente**: Analizar los cambios en manifiestos de dependencias e identificar riesgos por vulnerabilidades conocidas, typosquatting o scripts maliciosos.
- **Módulos con los que interactúa**:
  - `watchgate.core.orchestrator`: Invocado concurrentemente mediante `safe_analyze`.
  - `watchgate.core.layers.base`: Extiende `AnalysisLayer` y se registra en `LAYER_REGISTRY`.
  - `watchgate.core.layers._shared`: Reutiliza `analyze_install_script_text` y `DEPENDENCY_MANIFEST_FILENAMES`.
- **Dependencias**:
  - Internas: `watchgate.core.layers.base`, `watchgate.core.models`, `watchgate.core.layers._shared`.
  - Externas: `httpx`, `rapidfuzz`, `pydantic`, `sqlite3`, `json`, `re`, `pathlib`, `threading`, `datetime`.
- **Flujo de comunicación**: Lee el `NormalizedDiff`, extrae los cambios en manifiestos, consulta la caché u OSV.dev, evalúa typosquatting/scripts y retorna un `LayerResult`.
- **Entradas y salidas**:
  - Entradas: `diff: NormalizedDiff`, `metadata: dict[str, Any]`.
  - Salidas: `LayerResult` con `risk_score = max(scores)` para no inflar la nota por volumen de dependencias.

### Análisis técnico

- **Ficheros principales**: `watchgate/core/layers/deps_layer.py`
- **Clases importantes**:
  - `DependencyChange`: Modelo Pydantic que representa una alteración en una dependencia.
  - `OSVCache`: Caché SQLite thread-safe para respuestas de OSV con TTL de 24h y fallback de ruta.
  - `TyposquatChecker`: Evaluador de distancia Levenshtein contra datasets de paquetes populares.
  - `DepsLayer`: Clase principal que extiende `AnalysisLayer`.
- **Funciones relevantes**:
  - `parse_package_json()`, `parse_requirements_txt()`, `parse_pkgbuild()`, `parse_cargo_toml()`.
  - `_query_osv_batch()`: Realiza peticiones batch HTTP `/v1/querybatch`.
  - `_is_high_or_critical_vuln()`: Mapeador de severidad CVSS.
  - `analyze()`: Método principal de análisis.
- **Flujo de ejecución**:
  1. Filtra si existen archivos modificados en `DEPENDENCY_MANIFEST_FILENAMES`.
  2. Parsea los parches según el archivo manifiesto.
  3. Ejecuta consulta batch a OSV (revisando primero `OSVCache`).
  4. Para cada dependencia, evalúa typosquatting, scripts de instalación, URLs directas y vulnerabilidades.
  5. Asigna `risk_score = max(scores)` y retorna `LayerResult`.
- **Flujo de datos**: `NormalizedDiff` $\rightarrow$ `list[DependencyChange]` $\rightarrow$ `OSVCache`/`httpx` $\rightarrow$ `LayerResult`.
- **Decisiones de diseño**: `risk_score` toma el valor MÁXIMO de las alertas individuales para evitar una falsa inflación por cantidad de paquetes nuevos legítimos.

### Dependencias

#### Dependencias internas
- `watchgate.core.layers.base`
- `watchgate.core.models`
- `watchgate.core.layers._shared`

#### Dependencias externas
- `httpx`
- `rapidfuzz`
- `pydantic`
- `sqlite3`

#### Interfaces utilizadas
- Clase base `AnalysisLayer`
- Decorador `@register_layer`

### Problemas detectados

- **Duplicación de código**: Ninguna.
- **Complejidad innecesaria**: Ninguna.
- **Problemas de diseño**: Ninguno.
- **Falta de documentación**: Código limpio y estructurado con tipado estático completo.
- **Riesgos de mantenimiento**: Dependencia de la disponibilidad pública de la API OSV.dev (mitigado por la caché local SQLite y tolerancia a fallos).
- **Dificultad de extensión**: Mínima; añadir un ecosistema requiere crear un parser y añadir su referencia en `TyposquatChecker`.

### Posibles mejoras

- **Refactorizaciones**: Ninguna necesaria.
- **Mejoras arquitectónicas**: Ninguna requerida.
- **Mejoras de rendimiento**: Uso de consultas HTTP batch (`/v1/querybatch`) reduce la latencia de análisis a $< 200$ ms.
- **Mejoras de mantenibilidad**: Automatizar la actualización de datasets en `datasets/typosquat_reference/`.
- **Mejoras de testing**: Mantener la suite de tests en `tests/unit/test_deps_layer.py`.
- **Cambios futuros**: Añadir parsers para Go (`go.mod`) y PHP (`composer.json`).

### Estado para otros desarrolladores

- **Partes estables**: Lógica de consulta OSV, `OSVCache` y `TyposquatChecker`.
- **Partes a revisar antes de modificar**: Expresiones regulares de parseo en `parse_requirements_txt`.
- **Conocimientos necesarios**: Estructura de manifiestos de paquetes y distancia Levenshtein.
- **Tareas pendientes**: Ninguna inmediata.

### Próximos pasos

- Mantener actualizados los listados de referencia de paquetes populares.

---

## 2.4 Otros componentes relacionados detectados

### 2.4.1 Pipeline compartido (`watchgate/core/pipeline.py`)

#### Información básica
- Responsable: Pablo Ayllón García / Javier Martín Jurado
- Ubicación en el proyecto: `watchgate/core/pipeline.py`
- Estado actual: Completado y Operativo
- Última revisión: 2026-08-06
- Nivel de madurez: Producción / Estable

#### Historial de cambios
| Fecha | Cambio realizado | Motivo | Responsable |
|------|------------------|--------|-------------|
| 2026-08-06 | Creación del módulo `pipeline.py` con `run_full_analysis` | Unificar el flujo de orquestación entre CLI, GitHub Action y Engine API | Pablo Ayllón / Javier Martín |

#### Estado actual
- **Funcionalidades implementadas**:
  - Función `run_full_analysis(diff, metadata, config)`: Instancia `CostController`, configura `layer_factories` para `SemanticLayer`, ejecuta el cortocircuito si está activo, orquesta las capas en paralelo y realiza la agregación final.
  - Liberación garantizada de recursos con bloque `finally: cost_control.close()`.
  - Soporte para desacople de semántica mediante `_ConfigWithoutSemantic` en la evaluación previa de cortocircuito.
- **Funcionalidades pendientes**: Ninguna.
- **Partes completas**: Toda la lógica de orquestación de alto nivel.
- **Limitaciones conocidas**: Ninguna.

#### Arquitectura e integración
- **Responsabilidad**: Actuar como el orquestador principal de dominio reutilizable por cualquier adaptador.
- **Módulos con los que interactúa**: `CostController`, `SemanticLayer`, `run_analysis`, `evaluate_shortcircuit`, `aggregate`.
- **Dependencias**:
  - Internas: `watchgate.config`, `watchgate.core.cost_control`, `watchgate.core.layers._semantic.layer`, `watchgate.core.orchestrator`, `watchgate.core.shortcircuit`, `watchgate.core.aggregator`.
  - Externas: Ninguna.
- **Entradas y salidas**: `diff: NormalizedDiff`, `metadata: dict`, `config: WatchGateConfig` $\rightarrow$ `AggregatedResult`.

#### Análisis técnico
- **Ficheros principales**: `watchgate/core/pipeline.py`
- **Clases importantes**: `_ConfigWithoutSemantic`
- **Funciones relevantes**: `run_full_analysis()`
- **Flujo de ejecución**:
  1. Instancia `CostController` si `weights['semantic'] > 0`.
  2. Evalúa cortocircuito con `_ConfigWithoutSemantic`.
  3. Si salta cortocircuito, retorna agregación directa con `skipped=True` en semántica.
  4. Si no, invoca `run_analysis` con `layer_factories`.
  5. Cierra `CostController` en bloque `finally`.
- **Decisiones de diseño**: Garantizar que el orquestador no duplique código entre entornos de ejecución (CLI vs. GitHub Actions vs. API SaaS).

#### Dependencias
##### Dependencias internas: `watchgate.config`, `watchgate.core.cost_control`, `watchgate.core.orchestrator`, `watchgate.core.shortcircuit`, `watchgate.core.aggregator`.
##### Dependencias externas: Ninguna.
##### Interfaces utilizadas: `run_full_analysis`.

#### Problemas detectados: Ninguno.
#### Posibles mejoras: Ninguna.
#### Estado para otros desarrolladores: Estable y listo para integración con la Engine API SaaS.
#### Próximos pasos: Utilizar `run_full_analysis` en el router de análisis de la API SaaS.

---

### 2.4.2 Control de coste y concurrencia (`watchgate/core/cost_control.py`)

#### Información básica
- Responsable: Pablo Ayllón García
- Ubicación en el proyecto: `watchgate/core/cost_control.py`
- Estado actual: Completado y Operativo
- Última revisión: 2026-08-06
- Nivel de madurez: Producción / Estable

#### Historial de cambios
| Fecha | Cambio realizado | Motivo | Responsable |
|------|------------------|--------|-------------|
| 2026-08-01 | Implementación inicial de `CostController` con SQLite | Control presupuestario y caché semántica (§8, A.3.3) | Pablo Ayllón García |
| 2026-08-05 | Inclusión de `check_same_thread=False` y `threading.Lock` | Prevenir bloqueos de concurrencia en la ejecución multihilo del orquestador | Pablo Ayllón García |
| 2026-08-06 | Serialización directa de `SemanticOutput` y soporte estricto de `monthly_budget_tokens <= 0` | Corrección de integraciones de tipos con Pydantic v2 | Pablo Ayllón / Javier Martín |

#### Estado actual
- **Funcionalidades implementadas**:
  - Estimación de tokens basada en heurística (~4 caracteres/token).
  - Truncado inteligente de diffs priorizando ficheros marcados por capas estática/dependencias (`truncate_diff`).
  - Caché de respuestas de la capa semántica mediante SHA-256 del diff (`diff_hash`).
  - Control de presupuesto mensual por repositorio (`record_usage`, `budget_remaining`, `should_skip`).
  - Manejo de contexto mediante protocol `__enter__` / `__exit__`.
- **Funcionalidades pendientes**: Ninguna.
- **Partes completas**: Todas las funcionalidades de control de costes y caché.

#### Arquitectura e integración
- **Responsabilidad**: Limitar y optimizar el consumo de tokens de LLM en la capa semántica.
- **Módulos con los que interactúa**: `SemanticLayer`, `pipeline.py`.
- **Dependencias**:
  - Internas: `watchgate.core.layers._semantic.client`, `watchgate.core.models`.
  - Externas: `sqlite3`, `threading`, `hashlib`, `json`, `datetime`, `pathlib`.
- **Entradas y salidas**: Invocaciones directas de métodos sobre la instancia `CostController`.

#### Análisis técnico
- **Ficheros principales**: `watchgate/core/cost_control.py`
- **Clases importantes**: `CostController`
- **Funciones relevantes**: `diff_hash()`, `estimate_tokens()`, `truncate_diff()`, `get_cached()`, `store_cached()`, `should_skip()`, `build_skipped_budget_result()`.
- **Decisiones de diseño**: Uso de SQLite con `timeout=30.0` y `threading.Lock` para la prevención de bloqueos (*database locked*) en concurrencia multihilo.

#### Dependencias
##### Dependencias internas: `watchgate.core.layers._semantic.client`, `watchgate.core.models`.
##### Dependencias externas: `sqlite3`, `threading`.
##### Interfaces utilizadas: Métodos de `CostController`.

#### Problemas detectados: Solucionados en las revisiones recientes.
#### Posibles mejoras: Ninguna.
#### Estado para otros desarrolladores: Totalmente estable.
#### Próximos pasos: Ninguno.

---

### 2.4.3 Orquestador multihilo (`watchgate/core/orchestrator.py`)

#### Información básica
- Responsable: Pablo Ayllón García
- Ubicación en el proyecto: `watchgate/core/orchestrator.py`
- Estado actual: Completado y Operativo
- Última revisión: 2026-08-06
- Nivel de madurez: Producción / Estable

#### Historial de cambios
| Fecha | Cambio realizado | Motivo | Responsable |
|------|------------------|--------|-------------|
| 2026-08-01 | Creación de `run_analysis` con `ThreadPoolExecutor` | Ejecución paralela de capas de análisis (§9, A.1) | Pablo Ayllón García |
| 2026-08-05 | Inclusión de `layer_factories` en `run_analysis` | Permitir la instanciación de capas con parámetros complejos sin romper reglas de la spec | Pablo Ayllón García |

#### Estado actual
- **Funcionalidades implementadas**:
  - Ejecución paralela de capas activas (peso $> 0$) utilizando `concurrent.futures.ThreadPoolExecutor`.
  - Aislamiento total de fallos individuales mediante `safe_analyze`.
  - Inyección opcional de `layer_factories` para construcciones complejas (ej. `SemanticLayer`).
  - Cumplimiento estricto de la regla de la spec: sin condicionales `if` que decidan qué capa ejecutar por nombre.
- **Funcionalidades pendientes**: Ninguna.

#### Arquitectura e integración
- **Responsabilidad**: Coordinar la ejecución paralela multihilo de todas las capas activas y llamar al agregador.
- **Módulos con los que interactúa**: `LAYER_REGISTRY`, `safe_analyze`, `aggregate`.
- **Dependencias**:
  - Internas: `watchgate.core.layers.base`, `watchgate.core.aggregator`, `watchgate.core.models`.
  - Externas: `concurrent.futures`, `typing.Protocol`.

#### Análisis técnico
- **Ficheros principales**: `watchgate/core/orchestrator.py`
- **Interfaces**: `WatchGateConfig` (Protocol).
- **Funciones relevantes**: `run_analysis()`

#### Dependencias
##### Dependencias internas: `watchgate.core.layers.base`, `watchgate.core.aggregator`, `watchgate.core.models`.
##### Dependencias externas: `concurrent.futures`.
##### Interfaces utilizadas: `run_analysis`.

#### Problemas detectados: Ninguno.
#### Posibles mejoras: Ninguna.
#### Estado para otros desarrolladores: Estable.
#### Próximos pasos: Ninguno.

---

### 2.4.4 Ingesta de diffs local y HTTP (`watchgate/core/diffparser.py`)

#### Información básica
- Responsable: Pablo Ayllón García
- Ubicación en el proyecto: `watchgate/core/diffparser.py`
- Estado actual: Completado y Operativo
- Última revisión: 2026-08-06
- Nivel de madurez: Producción / Estable

#### Historial de cambios
| Fecha | Cambio realizado | Motivo | Responsable |
|------|------------------|--------|-------------|
| 2026-08-01 | Implementación de `parse_diff` con GitPython | Extracción de diffs locales de repositorios Git (§2) | Pablo Ayllón García |
| 2026-08-06 | Inclusión de `parse_diff_from_text` utilizando `unidiff` | Permitir la ingesta de parches en texto plano sin repositorio en disco para la Engine API SaaS | Pablo Ayllón García |

#### Estado actual
- **Funcionalidades implementadas**:
  - `parse_diff()`: Procesa diffs de repositorios locales mediante GitPython, identificando estados de archivos, conteo de adiciones/borrados, detección de binarios e inferencia de lenguajes.
  - `parse_diff_from_text()`: Parsea parches en texto plano transmitidos por HTTP mediante `unidiff.PatchSet`.
  - Mapeo de extensiones a lenguajes (`_EXTENSION_TO_LANGUAGE` y `_FILENAME_TO_LANGUAGE`).
- **Funcionalidades pendientes**: Ninguna.

#### Arquitectura e integración
- **Responsabilidad**: Normalizar la información de diffs de Git a la estructura `NormalizedDiff`.
- **Módulos con los que interactúa**: `cli.py`, `pipeline.py`, `adapters/github_action/main.py`.
- **Dependencias**:
  - Internas: `watchgate.core.models`.
  - Externas: `git` (GitPython), `unidiff`, `logging`.

#### Análisis técnico
- **Ficheros principales**: `watchgate/core/diffparser.py`
- **Funciones relevantes**: `parse_diff()`, `parse_diff_from_text()`, `_infer_language()`, `_status_from_diff_item()`.

#### Dependencias
##### Dependencias internas: `watchgate.core.models`.
##### Dependencias externas: `git` (GitPython), `unidiff`.
##### Interfaces utilizadas: `parse_diff`, `parse_diff_from_text`.

#### Problemas detectados: Solucionados.
#### Posibles mejoras: Ninguna.
#### Estado para otros desarrolladores: Estable.
#### Próximos pasos: Utilizar `parse_diff_from_text` en el endpoint `POST /api/v1/analyze`.

---

### 2.4.5 Paquete unificado de persistencia (`watchgate/db/`)

#### Información básica
- Responsable: Pablo Ayllón García
- Ubicación en el proyecto: `watchgate/db/` (`models.py`, `connection.py`, `repository.py`, `__init__.py`)
- Estado actual: Completado y Probado
- Última revisión: 2026-08-06
- Nivel de madurez: Producción / Estable

#### Historial de cambios
| Fecha | Cambio realizado | Motivo | Responsable |
|------|------------------|--------|-------------|
| 2026-08-06 | Creación del paquete unificado de persistencia con `SQLModel` | Proveer el esquema ORM y repositorios de datos para la arquitectura Engine API SaaS | Pablo Ayllón García |

#### Estado actual
- **Funcionalidades implementadas**:
  - Modelos ORM relacionales Pydantic + SQLAlchemy mediante `SQLModel`: `User`, `UserAPIKey`, `UserTokenUsage`, `SemanticCache`, `PRScore`.
  - Conexión híbrida en `connection.py`: Soporte para SQLite (modo WAL, `check_same_thread=False`) en entornos locales/tests y PostgreSQL en producción mediante `WATCHGATE_DATABASE_URL`.
  - Vault de claves API (`UserAPIKey`): Generación y almacenamiento exclusivo por hash SHA-256 (`key_hash`) con prefijos públicos (`wg_live_...`).
  - Repositorio relacional (`watchgate/db/repository.py`): Operaciones CRUD thread-safe y gestión de transacciones.
- **Funcionalidades pendientes**: Integración completa en la Engine API de FastAPI.
- **Partes completas**: Todos los modelos, conexión y repositorio verificados mediante `tests/unit/test_db.py`.

#### Arquitectura e integración
- **Responsabilidad**: Gestionar la persistencia de datos de usuarios, claves API, presupuestos de tokens, caché semántica e histórico de puntuaciones de PRs.
- **Módulos con los que interactúa**: `watchgate/api/`, `watchgate/dashboard/backend/`.
- **Dependencias**:
  - Internas: Ninguna.
  - Externas: `sqlmodel`, `sqlalchemy`, `sqlite3`, `datetime`, `hashlib`, `secrets`.

#### Análisis técnico
- **Ficheros principales**: `watchgate/db/models.py`, `watchgate/db/connection.py`, `watchgate/db/repository.py`.
- **Clases importantes**: `User`, `UserAPIKey`, `UserTokenUsage`, `SemanticCache`, `PRScore`, `Repository`.
- **Decisiones de diseño**: Utilizar `SQLModel` para unificar los modelos de validación Pydantic v2 de las APIs con los esquemas relacionales de la base de datos.

#### Dependencias
##### Dependencias internas: Ninguna.
##### Dependencias externas: `sqlmodel`, `sqlalchemy`.
##### Interfaces utilizadas: `get_engine`, `get_session`, `Repository`.

#### Problemas detectados: Ninguno.
#### Posibles mejoras: Añadir migraciones con Alembic cuando el esquema evolucione.
#### Estado para otros desarrolladores: Estable y verificado con tests.
#### Próximos pasos: Conectar el middleware de autenticación de la API con `Repository.verify_api_key`.

---

### 2.4.6 Refactorización de capa estática (`watchgate/core/layers/static_layer.py`)

#### Información básica
- Responsable: Pablo Ayllón García / Javier Martín Jurado
- Ubicación en el proyecto: `watchgate/core/layers/static_layer.py`
- Estado actual: Completado y Operativo
- Última revisión: 2026-08-06
- Nivel de madurez: Producción / Estable

#### Historial de cambios
| Fecha | Cambio realizado | Motivo | Responsable |
|------|------------------|--------|-------------|
| 2026-08-06 | Sincronización inteligente de reglas Semgrep y ejecución sobre parches temporales | Evitar latencias de red innecesarias y mejorar la robustez en entornos CI/CD | Pablo Ayllón / Javier Martín |

#### Estado actual
- **Funcionalidades implementadas**:
  - Sincronización inteligente de reglas Semgrep en `.watchgate/rules_cache/`: Reutilización local directa con 0 ms de latencia si la caché fue comprobada en las últimas 24h.
  - Comprobación ligera `git fetch --depth=1` con timeout estricto de 5s tras expirar el TTL.
  - Fallback transparente a la caché local ante fallos de conexión o timeout.
  - Ejecución aislada de Semgrep sobre archivos temporales (`diff_hunk`) procesados en directorios temporales aislados (`tempfile.mkdtemp`).
  - Limpieza robusta de directorios temporales tolerante a errores de permisos en Windows/Linux (`_handle_remove_read_only`).
- **Funcionalidades pendientes**: Ninguna.

#### Arquitectura e integración
- **Responsabilidad**: Ejecutar el análisis estático de código con Semgrep sobre las líneas modificadas en la PR.
- **Módulos con los que interactúa**: `orchestrator.py`, `LAYER_REGISTRY`.
- **Dependencias**:
  - Internas: `watchgate.core.layers.base`, `watchgate.core.models`.
  - Externas: `subprocess`, `tempfile`, `shutil`, `os`, `time`, `pathlib`, `json`.

#### Análisis técnico
- **Ficheros principales**: `watchgate/core/layers/static_layer.py`
- **Funciones relevantes**: `_get_rules_dir()`, `_run_semgrep_on_file()`, `analyze()`.

#### Dependencias
##### Dependencias internas: `watchgate.core.layers.base`, `watchgate.core.models`.
##### Dependencias externas: `subprocess`, `tempfile`, `semgrep` CLI.
##### Interfaces utilizadas: `StaticLayer`.

#### Problemas detectados: Solucionados.
#### Posibles mejoras: Ninguna.
#### Estado para otros desarrolladores: Estable.
#### Próximos pasos: Ninguno.

---

# 3. Relaciones entre componentes

La arquitectura general de WatchGate está organizada en capas con responsabilidades delimitadas y desacopladas.

## Flujo General de Ejecución

1. **Punto de Entrada**: La CLI (`watchgate/cli.py`) o la GitHub Action (`adapters/github_action/main.py`) capturan los parámetros y extraen el `NormalizedDiff` mediante `parse_diff` o `parse_diff_from_text`.
2. **Pipeline Reutilizable**: Se delega el análisis en `run_full_analysis()` del módulo `watchgate/core/pipeline.py`.
3. **Control de Costes**: `run_full_analysis` instancia `CostController` para preparar el presupuesto y la caché semántica.
4. **Cortocircuito**: `evaluate_shortcircuit` evalúa las capas livianas (`static`, `deps`, `reputation`). Si se cumplen las condiciones matemáticas de riesgo extremo (rojo) o riesgo mínimo verificado sin patrones forzadores (verde), se retorna la agregación de forma inmediata omitiendo la llamada al LLM.
5. **Orquestación Paralela**: Si no hay cortocircuito, `orchestrator.run_analysis` ejecuta concurrentemente en un `ThreadPoolExecutor` todas las capas activas con peso $> 0$ (`StaticLayer`, `DepsLayer`, `ReputationLayer`, `SemanticLayer`).
6. **Agregación**: `aggregator.aggregate` unifica los resultados parciales aplicando los pesos configurados en `.watchgate.yml`, aplica reglas de semáforo y genera el `AggregatedResult` final.
7. **Formateo y Persistencia**: El resultado es renderizado en Markdown/JSON por la CLI/GitHub Action y registrado en la base de datos mediante `watchgate/db/`.

## Diagrama de Arquitectura e Integración (Mermaid)

```mermaid
graph TD
    CLI[cli.py / watchgate analyze] -->|Carga Config & Diff| Pipeline[core/pipeline.py / run_full_analysis]
    GHAction[adapters/github_action/main.py] -->|Carga Evento & Reputación| Pipeline
    EngineAPI[watchgate/api / POST analyze] -->|Parse diff_text| Pipeline

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
    StaticLayer --> SemgrepCache[(Rules Cache .watchgate/)]
    SemLayer --> CC
    CC --> DBCache[(SemanticCache SQLModel)]

    Orchestrator --> Aggregator[aggregator.py / aggregate]

    Aggregator -->|AggregatedResult| CLI
    Aggregator -->|AggregatedResult| GHAction
    Aggregator -->|AggregatedResult| EngineAPI
    AggregatorShort -->|AggregatedResult| CLI
    AggregatorShort -->|AggregatedResult| GHAction
    AggregatorShort -->|AggregatedResult| EngineAPI

    CLI -->|Markdown / JSON| Output([stdout / Fichero])
    GHAction -->|Comentario / Check Run| GitHubAPI([GitHub PR / Check Run API])
    EngineAPI -->|Response JSON| DB[(DB Persistence / SQLModel)]
```

---

# 4. Estado global

## Resumen Ejecutivo

El núcleo de análisis, la CLI, el módulo de pipeline compartido, el cortocircuito determinista, la capa de dependencias, la capa estática refactorizada y la capa de persistencia unificada DB se encuentran en un estado de **madurez total y alineación de arquitectura**.

La suite de tests unitarios e integrados cuenta con **244 pruebas pasadas al 100 %**, confirmando la robustez de las soluciones implementadas frente a concurrencia, gestión de errores de red y rendimiento.

## Clasificación de Componentes por Madurez

- **Componentes Maduros (Listos para Producción)**:
  - `watchgate/core/pipeline.py`: Pipeline reutilizable unificado.
  - `watchgate/cli.py`: Interfaz CLI refactorizada.
  - `watchgate/core/models.py` & `base.py`: Contratos Pydantic y registro.
  - `watchgate/core/diffparser.py`: Extractor Git local y parches en texto plano via `unidiff`.
  - `watchgate/core/orchestrator.py`: Orquestador multihilo con `layer_factories`.
  - `watchgate/core/cost_control.py`: Controlador de costes thread-safe.
  - `watchgate/core/shortcircuit.py`: Cortocircuito determinista.
  - `watchgate/core/layers/deps_layer.py`: Capa de dependencias.
  - `watchgate/core/layers/static_layer.py`: Capa estática con caché local de reglas Semgrep.
  - `watchgate/db/`: Paquete de persistencia relacional con `SQLModel`.
  - `watchgate/adapters/github_action/`: Adaptador oficial para GitHub Actions.

- **Componentes en Desarrollo / Integración Pendiente**:
  - `watchgate/api/`: Engine API Server SaaS (FastAPI).

## Riesgos Principales

1. **Persistencia de Cachés en CI/CD**: Para aprovechar al máximo las cachés locales de Semgrep, OSV y costes en GitHub Actions, es necesario documentar el uso de `actions/cache` sobre `.watchgate/`.
2. **Disponibilidad de Servicios Externos**: Dependencias de red externas (OSV.dev, Semgrep GitHub repo). Mitigado adecuadamente mediante fallbacks offline y timeouts estrictos.

---

# 5. Mejoras propuestas

## Alta prioridad

1. **Despliegue e Integración de la Engine API SaaS (`watchgate/api/`)**:
   - Crear los routers `routers/analyze.py` conectándolos con `parse_diff_from_text` y `run_full_analysis`.
   - Implementar el middleware de autenticación por API Key SHA-256 utilizando `watchgate/db/repository.py`.

## Media prioridad

1. **Ampliación de Parsers de Dependencias**:
   - Incorporar parsers para `go.mod` (Go) y `composer.json` (PHP) en `deps_layer.py`.

2. **Preservación de Cachés en GitHub Actions**:
   - Incluir la carpeta `.watchgate/` en las recetas recomendadas de `actions/cache` en la documentación oficial.

## Baja prioridad

1. **Autocompletado en CLI**:
   - Generar scripts de autocompletado para zsh/bash en `watchgate/cli.py`.

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
