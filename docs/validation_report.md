# Informe de validación — suite de aceptación (spec §14)

Generado automáticamente el 2026-08-10 09:04 UTC ejecutando `tests/integration/generate_validation_report.py` contra la API real de Gemini. No editar a mano -- regenerar con ese comando para que refleje el código actual. Resultados en bruto de cada caso en `docs/validation_report_raw.json`.

**Resultado global: 180/193 casos dentro de lo esperado (93%).**

> Score calculado con las 5 capas reales (`static` 0.25, `dependencies` 0.10, `vulnerabilities` 0.10, `reputation` 0.15, `semantic` 0.40) -- ver `tests/integration/pipeline_runner.py` para la nota histórica sobre por qué informes anteriores a este solo reflejaban `reputation`+`semantic`.

## Resumen por clase y dificultad

| Clase | Dificultad | N | OK | % OK |
|---|---|---:|---:|---:|
| benign | easy | 21 | 21 | 100% |
| benign | hard | 41 | 41 | 100% |
| benign | medium | 58 | 56 | 96% |
| canonico | - | 18 | 16 | 88% |
| malicious | easy | 21 | 18 | 85% |
| malicious | hard | 11 | 9 | 81% |
| malicious | medium | 23 | 19 | 82% |

## Resumen de casos maliciosos por naturaleza de amenaza detectada

Desglose de los casos `class=malicious` (mezclan ataques -- código malicioso/backdoors -- y vulnerabilidades -- dependencias con CVEs conocidos -- bajo una sola etiqueta) por la naturaleza que el propio sistema les asignó realmente (`threat_summary`, el mismo campo que ya usa el comentario de PR real). `-` significa que ninguna capa activa reportó un `Finding` con `threat_nature` -- típicamente un falso negativo total, no solo una naturaleza mal clasificada.

| Naturaleza detectada | N | OK | % OK |
|---|---:|---:|---:|
| ataque | 43 | 43 | 100% |
| incertidumbre | 8 | 1 | 12% |
| vulnerabilidad | 3 | 2 | 66% |
| - | 1 | 0 | 0% |

## Casos que divergen de lo esperado (13)

| Caso | Esperado | Obtenido | Naturaleza | Categoría | Justificación (semántica) |
|---|---|---|---|---|---|
| `real_encode_httpx_3690` | verde/amarillo (min. 0) | rojo (100) | ataque | ofuscacion | La definición duplicada de la función `wait_ready` en `src/ahttpx/_parsers.py` (y en `src/httpx/_parsers.py`), donde la segunda definición sobrescribe la primera, es un patrón de ofuscación que dificulta la revisión de c |
| `real_pydantic_pydantic_13578` | verde/amarillo (min. 0) | rojo (100) | ataque | backdoor | El fichero uv.lock, que debería ser un lockfile de dependencias, contiene múltiples entradas para el paquete 'cryptography' con la versión '50.0.0', que tiene una fecha de subida (upload-time) del 31 de julio de 2026, un |
| `false_positive_candidate` | amarillo (min. 20) | rojo (70) | vulnerabilidad | escalada_privilegios | La función `evaluate_formula` en la línea 10 utiliza `eval()` para evaluar expresiones proporcionadas por el usuario, lo que, a pesar de los intentos de restringir el `namespace` y deshabilitar `__builtins__`, abre una s |
| `real_click_deprecate_isolated_fs` | verde/amarillo (min. 0) | rojo (70) | incertidumbre | backdoor | El diff incluye múltiples ficheros bytecode de Python (.pyc) que no deberían ser parte del control de versiones, y el contenido de todos los ficheros listados es 'no verificado' y no se pudo leer, impidiendo cualquier an |
| `malreal_npm_compromised_lib_graphql-sequelize-teselagen_14` | rojo (min. 70) | verde (2) | incertidumbre | ninguna | El fichero nuevo `base64.js` implementa funciones estándar de codificación y decodificación base64 usando el objeto Buffer de Node.js, sin ninguna lógica maliciosa, llamadas de red o dependencias inusuales. |
| `malreal_npm_compromised_lib_tvi-cli_55` | rojo (min. 70) | verde (28) | vulnerabilidad | exfiltracion | El middleware establece una política CORS que permite credenciales ('Access-Control-Allow-Credentials: true') y configura el origen permitido ('Access-Control-Allow-Origin') a una variable de entorno ('process.env.CORS_O |
| `malreal_pypi_compromised_lib_mflux-streamlit_6` | rojo (min. 70) | verde (2) | incertidumbre | ninguna | El cambio introduce un nuevo script `main.py` que simplemente actúa como un punto de entrada para iniciar una aplicación Streamlit existente (`app.py`) usando `subprocess.run()`, sin lógica adicional que sugiera comporta |
| `malreal_npm_compromised_lib__asyncapi_protobuf-schema-parser_150` | amarillo/rojo (min. 35) | verde (4) | incertidumbre | ninguna | El fichero nuevo añade una utilidad para convertir esquemas Protobuf a JSON Schema. El código no contiene llamadas de red sospechosas, ejecución de comandos externos ni manipulación de dependencias no seguras. Además, pr |
| `malreal_pypi_compromised_lib_xinference_11` | amarillo/rojo (min. 35) | verde (2) | incertidumbre | ninguna | El fichero nuevo añade una interfaz de chat con soporte para audio, decodificando datos base64 y escribiéndolos en un fichero temporal para reproducirlos en la interfaz, sin realizar llamadas de red externas no justifica |
| `malreal_npm_compromised_lib__tallyui_storage-sqlite_218` | rojo (min. 55) | verde (2) | incertidumbre | ninguna | El cambio añade un nuevo fichero de test de integración para RxDB con un mock de SQLite en memoria, utilizando patrones de testing estándar y sin acceso a recursos externos o sensibles. |
| `malreal_npm_malicious_intent_bambang-mangut66-sukiwir_14` | rojo (min. 55) | verde (19) | - | - |  |
| `malreal_npm_malicious_intent_jstoauto_26` | rojo (min. 55) | verde (13) | incertidumbre | ninguna | El cambio consiste en la adición de un nuevo archivo 'tools.js' que implementa utilidades para un sistema de logging (pino), sin presentar llamadas a red externas, ofuscación, ejecución de comandos arbitrarios ni manipul |
| `malreal_pypi_compromised_lib_lightning_5` | rojo (min. 55) | verde (2) | incertidumbre | ninguna | El cambio añade un nuevo módulo para lanzar y gestionar subprocesos para computación distribuida (DDP), un patrón común en frameworks de ML. Las llamadas a `subprocess.Popen` y `os.kill` son intrínsecas a su función legí |
