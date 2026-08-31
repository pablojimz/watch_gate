# Documentación de WatchGate

Índice de la documentación de uso y mantenimiento de la herramienta. Lo que
no aparece aquí (diarios de progreso, planificación interna del equipo,
presentación del premio, notas de trabajo con Claude) es material interno
del proceso de desarrollo, no documentación del producto -- se mantiene
fuera del repositorio público (ver `.gitignore`).

## Arquitectura y especificación

- [`WatchGate_spec_implementacion_IA.md`](WatchGate_spec_implementacion_IA.md)
  — especificación de construcción módulo a módulo: interfaz exacta,
  algoritmo, esquema y criterio de aceptación de cada componente. Referencia
  autoritativa para implementar o modificar cualquier pieza del sistema.

## Manuales de uso e integración

- [`manual_cli.md`](manual_cli.md) — uso de la CLI `watchgate` (formatos de
  salida, overrides de pesos/umbrales, ingesta por stdin, SARIF...).
- [`manual_mcp.md`](manual_mcp.md) — servidor MCP de WatchGate (Model
  Context Protocol).
- [`manual_rag.md`](manual_rag.md) — sistema RAG de la capa semántica
  (corpus, indexado, `watchgate rag reindex`).
- [`manual_git_hooks.md`](manual_git_hooks.md) — hooks `pre-receive`
  (servidor Git propio) y `pre-push` (cliente), y su relación con la
  GitHub Action.
- [`integracion_repo_reglas.md`](integracion_repo_reglas.md) — cómo
  `watch_gate` consume el repo privado de reglas Semgrep/YARA
  (`sync-rules.yml`/`reconcile-rules.yml`).

## Despliegue

- [`despliegue.md`](despliegue.md) — desplegar WatchGate más allá de un
  checkout local (Docker Compose, servicios).
- [`manual_despliegue_prod.md`](manual_despliegue_prod.md) — despliegue en
  producción con TLS y reverse proxy.
- [`despliegue_gpu_modelos_locales.md`](despliegue_gpu_modelos_locales.md)
  — levantar WatchGate en una máquina con GPU para probar modelos LLM
  locales.

## Mantenimiento del entorno de desarrollo

- [`manual_desarrollo.md`](manual_desarrollo.md) — guía del entorno de
  desarrollo y mantenimiento del proyecto.

## Calidad, precisión y decisiones de arquitectura de IA

Justificación técnica de por qué el motor está construido así — útil al
evaluar cambios en el proveedor LLM, el RAG o el dataset de referencia:

- [`validation_report.md`](validation_report.md) (+
  [`validation_report_raw.json`](validation_report_raw.json)) — informe de
  validación de la suite de aceptación contra la API real de Gemini
  (precisión medida por clase/dificultad). Se regenera con
  `tests/integration/generate_validation_report.py`, no se edita a mano.
- [`evaluacion_ia/comparativa_rag_modelos.md`](evaluacion_ia/comparativa_rag_modelos.md)
  — comparativa de modelos para la capa semántica/RAG.
- [`evaluacion_ia/rag_ablation_benchmark.md`](evaluacion_ia/rag_ablation_benchmark.md)
  — ¿aporta señal el RAG en la capa semántica? Comparativa con/sin RAG.
- [`evaluacion_ia/GEMINI_MODELS_CATALOG.md`](evaluacion_ia/GEMINI_MODELS_CATALOG.md)
  — catálogo de modelos de Google AI Studio evaluados.
- [`evaluacion_ia/ground_truth_dudoso_dataset_datadog.md`](evaluacion_ia/ground_truth_dudoso_dataset_datadog.md)
  — casos con ground truth no fiable detectados en el dataset `malreal_*`
  de DataDog, verificados contra la fuente original.

## Licencias de terceros

- [`../rules/semgrep/NOTICE.md`](../rules/semgrep/NOTICE.md) — reglas
  Semgrep de terceros (MIT / AGPL-3.0 / LGPL-2.1+Commons Clause según
  fuente).
- [`../rules/yara/NOTICE.md`](../rules/yara/NOTICE.md) — reglas YARA
  derivadas de Yara-Rules/rules (GPL-2.0).
