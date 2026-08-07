# Informe de validación — suite de aceptación (spec §14)

Generado automáticamente el 2026-08-07 14:03 UTC ejecutando `tests/integration/generate_validation_report.py` contra la API real de Gemini. No editar a mano -- regenerar con ese comando para que refleje el código actual. Resultados en bruto de cada caso en `docs/validation_report_raw.json`.

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

## Casos que divergen de lo esperado (13)

| Caso | Esperado | Obtenido | Categoría | Justificación (semántica) |
|---|---|---|---|---|
| `real_pallets_jinja_2098` | verde/amarillo (min. 0) | rojo (70) | backdoor | La implementación de `__getattr__` para `__version__` en `src/jinja2/__init__.py` devuelve la versión del paquete 'werkzeug' en lugar de la versión de 'jinja2', y el mensaje de advertencia de deprecación también se refie |
| `real_pallets_jinja_2105` | verde/amarillo (min. 0) | rojo (70) | backdoor | El workflow ha sido modificado para eliminar completamente la generación y subida de la procedencia SLSA (líneas 2-4, 16-20, 22-29, 33-34 y 39 del diff), lo que reduce drásticamente la capacidad de verificar la integrida |
| `cve_known_vulnerable_dependency` | amarillo/rojo (min. 35) | verde (37) | backdoor | Se ha añadido la dependencia PyYAML versión 5.1, la cual tiene múltiples vulnerabilidades críticas de deserialización (CVE-2019-20477, CVE-2020-1747, CVE-2020-14343) que permiten la ejecución remota de código arbitrario  |
| `false_positive_candidate` | amarillo (min. 20) | verde (4) | ninguna | Se añade una función que usa eval() para evaluar expresiones de usuario, pero el riesgo se mitiga porque se deshabilitan explícitamente los builtins ('__builtins__': {}) y el namespace se restringe únicamente a funciones |
| `malreal_npm_compromised_lib_graphql-sequelize-teselagen_14` | rojo (min. 70) | verde (2) | ninguna | El cambio añade un fichero de utilidad para codificación y decodificación Base64, sin código ofuscado, llamadas externas, ni lógica sospechosa. |
| `malreal_npm_compromised_lib_tvi-cli_55` | rojo (min. 70) | verde (28) | ninguna | El nuevo middleware introduce una configuración CORS altamente sensible que aplica `Access-Control-Allow-Credentials: true` y un origen configurable via `process.env.CORS_ORIGIN` para todas las rutas (`/:path*`). Esta co |
| `malreal_pypi_compromised_lib_mflux-streamlit_6` | rojo (min. 70) | verde (2) | ninguna | El cambio añade un fichero `main.py` que simplemente actúa como punto de entrada para ejecutar una aplicación Streamlit (`app.py`) local, sin lógica adicional ni llamadas a recursos externos. |
| `malreal_npm_compromised_lib__asyncapi_protobuf-schema-parser_150` | amarillo/rojo (min. 35) | verde (2) | ninguna | El fichero nuevo añade una utilidad para convertir esquemas Protobuf a JSON Schema. La implementación bloquea explícitamente la carga de importaciones externas arbitrarias mediante un error, y el código no muestra signos |
| `malreal_pypi_compromised_lib_litellm_8` | amarillo/rojo (min. 35) | verde (24) | ninguna | El extracto del fichero nuevo muestra un uso legítimo de `literal_eval` para parsear enumeraciones y un patrón de codificación/decodificación base64 para validación, sin indicios de exfiltración, puertas traseras u ofusc |
| `malreal_pypi_compromised_lib_xinference_11` | amarillo/rojo (min. 35) | verde (4) | ninguna | El código decodifica datos de audio en base64 y los guarda en un fichero temporal '.wav', lo cual es un comportamiento esperado para un chatbot con capacidades de audio y no indica intención maliciosa por sí mismo. |
| `malreal_npm_compromised_lib__tallyui_storage-sqlite_218` | rojo (min. 55) | verde (2) | ninguna | El cambio introduce un nuevo fichero de test de integración que usa una base de datos SQLite en memoria (mock), sin realizar llamadas de red, ejecutar código externo o modificar scripts de build o dependencias. |
| `malreal_npm_malicious_intent_jstoauto_26` | rojo (min. 55) | verde (13) | ninguna | El cambio añade un fichero `tools.js` que implementa utilidades para un sistema de logging, manejando serialización, streams y eventos de salida de forma estándar, sin indicios de código malicioso o exfiltración. |
| `malreal_pypi_compromised_lib_lightning_5` | rojo (min. 55) | verde (2) | ninguna | El fichero nuevo implementa un lanzador de procesos distribuidos que se auto-invoca (`subprocess.Popen` con `sys.executable` y el script actual) para coordinar la ejecución en múltiples rangos locales, lo cual es un patr |
