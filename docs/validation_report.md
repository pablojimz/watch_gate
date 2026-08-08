# Informe de validación — suite de aceptación (spec §14)

Generado automáticamente el 2026-08-08 23:14 UTC ejecutando `tests/integration/generate_validation_report.py` contra la API real de Gemini. No editar a mano -- regenerar con ese comando para que refleje el código actual. Resultados en bruto de cada caso en `docs/validation_report_raw.json`.

**Resultado global: 180/193 casos dentro de lo esperado (93%).**

> Score calculado con las 5 capas reales (`static` 0.25, `dependencies` 0.10, `vulnerabilities` 0.10, `reputation` 0.15, `semantic` 0.40) -- ver `tests/integration/pipeline_runner.py` para la nota histórica sobre por qué informes anteriores a este solo reflejaban `reputation`+`semantic`.

## Resumen por clase y dificultad

| Clase | Dificultad | N | OK | % OK |
|---|---|---:|---:|---:|
| benign | easy | 21 | 21 | 100% |
| benign | hard | 41 | 39 | 95% |
| benign | medium | 58 | 58 | 100% |
| canonico | - | 18 | 16 | 88% |
| malicious | easy | 21 | 18 | 85% |
| malicious | hard | 11 | 8 | 72% |
| malicious | medium | 23 | 20 | 86% |

## Resumen de casos maliciosos por naturaleza de amenaza detectada

Desglose de los casos `class=malicious` (mezclan ataques -- código malicioso/backdoors -- y vulnerabilidades -- dependencias con CVEs conocidos -- bajo una sola etiqueta) por la naturaleza que el propio sistema les asignó realmente (`threat_summary`, el mismo campo que ya usa el comentario de PR real). `-` significa que ninguna capa activa reportó un `Finding` con `threat_nature` -- típicamente un falso negativo total, no solo una naturaleza mal clasificada.

| Naturaleza detectada | N | OK | % OK |
|---|---:|---:|---:|
| ataque | 42 | 42 | 100% |
| incertidumbre | 9 | 1 | 11% |
| vulnerabilidad | 4 | 3 | 75% |

## Casos que divergen de lo esperado (13)

| Caso | Esperado | Obtenido | Naturaleza | Categoría | Justificación (semántica) |
|---|---|---|---|---|---|
| `real_pallets_jinja_2098` | verde/amarillo (min. 0) | rojo (100) | ataque | backdoor | La implementación de `__getattr__` para `__version__` en `src/jinja2/__init__.py` devuelve deliberadamente la versión del paquete 'werkzeug' en lugar de la versión de 'jinja2', y el mensaje de advertencia de deprecación  |
| `real_pallets_jinja_2105` | verde/amarillo (min. 0) | rojo (100) | ataque | ninguna | El diff elimina el job de generación de la proveniencia SLSA y los pasos asociados de hashing y subida de ficheros de proveniencia (`*.intoto.jsonl`), una característica crítica de seguridad en la cadena de suministro, d |
| `benign_new_feature_with_new_dep` | verde/amarillo (min. 0) | rojo (70) | vulnerabilidad | escalada_privilegios | Se añade una nueva dependencia 'click' en la versión 8.1.7, que tiene una vulnerabilidad de inyección de comandos (PYSEC-2026-2132) que permite a un atacante ejecutar comandos arbitrarios en el sistema -- este patrón es  |
| `false_positive_candidate` | amarillo (min. 20) | verde (4) | vulnerabilidad | ninguna | La función `evaluate_formula` utiliza `eval()` con un `__builtins__` vacío y un `namespace` controlado, limitando la ejecución a funciones matemáticas específicas y valores de celda, lo que mitiga significativamente el r |
| `malreal_npm_compromised_lib_graphql-sequelize-teselagen_14` | rojo (min. 70) | verde (2) | incertidumbre | ninguna | El cambio añade un fichero de utilidad para codificar y decodificar en base64 usando la clase `Buffer` de Node.js, sin indicios de ofuscación, exfiltración o ejecución remota. |
| `malreal_npm_compromised_lib_tvi-cli_55` | rojo (min. 70) | verde (32) | vulnerabilidad | ninguna | El middleware nuevo establece 'Access-Control-Allow-Credentials' a 'true' y define 'Access-Control-Allow-Origin' dinámicamente desde la variable de entorno 'process.env.CORS_ORIGIN' para todas las rutas. Esto introduce u |
| `malreal_pypi_compromised_lib_mflux-streamlit_6` | rojo (min. 70) | verde (2) | incertidumbre | ninguna | El cambio consiste en añadir un script principal que ejecuta una aplicación Streamlit local (`streamlit run app.py`) utilizando `subprocess.run()`, sin descargar código externo, modificar dependencias o interactuar con l |
| `malreal_npm_compromised_lib__asyncapi_protobuf-schema-parser_150` | amarillo/rojo (min. 35) | verde (2) | incertidumbre | ninguna | El fichero nuevo implementa un compilador de Protobuf a JSON Schema, sin llamadas de red externas sospechosas, ejecución de comandos del sistema, ni patrones de ofuscación o exfiltración. Las expresiones regulares se usa |
| `malreal_pypi_compromised_lib_xinference_11` | amarillo/rojo (min. 35) | verde (2) | incertidumbre | ninguna | El cambio consiste en añadir un nuevo fichero que implementa una interfaz de chat con Gradio, incluyendo el manejo de datos de audio codificados en base64 y guardados en ficheros temporales. Este comportamiento forma par |
| `malreal_pypi_malicious_intent_mirrorbot_10` | amarillo/rojo (min. 35) | verde (17) | incertidumbre | ninguna | El fichero contiene una colección de funciones para generar enlaces de descarga directa de múltiples servicios de alojamiento y acortadores, un patrón consistente con un propósito utilitario. Aunque interactúa con muchos |
| `malreal_npm_compromised_lib__tallyui_storage-sqlite_218` | rojo (min. 55) | verde (2) | incertidumbre | ninguna | El cambio consiste en un nuevo fichero de pruebas de integración para la funcionalidad de base de datos, utilizando dependencias locales simuladas y sin introducir llamadas de red, ejecución de código externo o cambios d |
| `malreal_npm_malicious_intent_jstoauto_26` | rojo (min. 55) | verde (13) | incertidumbre | ninguna | El cambio añade un nuevo módulo JavaScript que implementa lógica de logging, serialización y manejo de streams, con patrones de código consistentes con una biblioteca de logging como Pino, sin indicios de ofuscación mali |
| `malreal_pypi_compromised_lib_lightning_5` | rojo (min. 55) | verde (2) | incertidumbre | ninguna | El script añadido implementa un lanzador de procesos distribuidos que replica la ejecución del script actual, estableciendo variables de entorno comunes para entornos de entrenamiento distribuido y gestionando los proces |
