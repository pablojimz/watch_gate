# Informe de validación — suite de aceptación (spec §14)

Generado automáticamente el 2026-08-06 09:33 UTC ejecutando `tests/integration/generate_validation_report.py` contra la API real de Gemini. No editar a mano -- regenerar con ese comando para que refleje el código actual. Resultados en bruto de cada caso en `docs/validation_report_raw.json`.

**Resultado global: 182/191 casos dentro de lo esperado (95%).**

> `static_layer.py`/`deps_layer.py` (Línea 3) siguen sin implementar: el score de esta suite es la media ponderada renormalizada de `reputation` (0.15) + `semantic` (0.40) únicamente, no las 4 capas de la memoria §8.

## Resumen por clase y dificultad

| Clase | Dificultad | N | OK | % OK |
|---|---|---:|---:|---:|
| benign | easy | 21 | 21 | 100% |
| benign | hard | 41 | 40 | 97% |
| benign | medium | 58 | 58 | 100% |
| canonico | - | 18 | 17 | 94% |
| malicious | easy | 21 | 18 | 85% |
| malicious | hard | 10 | 9 | 90% |
| malicious | medium | 22 | 19 | 86% |

## Casos que divergen de lo esperado (9)

| Caso | Esperado | Obtenido | Categoría | Justificación (semántica) |
|---|---|---|---|---|
| `real_pallets_jinja_2105` | verde/amarillo (min. 0) | rojo (70) | backdoor | El cambio elimina la generación de SLSA provenance para los artefactos de build, incluyendo la computación de hashes (`sha256sum`) y el uso del `slsa-github-generator`, lo que impide verificar la integridad de los artefa |
| `false_positive_candidate` | amarillo (min. 20) | verde (7) | ninguna | Se añade una función 'evaluate_formula' que usa 'eval' para evaluar expresiones de usuario, pero con fuertes medidas de seguridad: '__builtins__' se establece a un diccionario vacío y el 'namespace' se limita estrictamen |
| `malreal_npm_compromised_lib_graphql-sequelize-teselagen_14` | rojo (min. 70) | verde (4) | ninguna | Se añade un nuevo módulo JavaScript que implementa funciones estándar de codificación y decodificación Base64 utilizando la API Buffer de Node.js, sin evidencia de ofuscación ni intención maliciosa. |
| `malreal_npm_compromised_lib_tvi-cli_55` | rojo (min. 70) | amarillo (55) | ninguna | El middleware añade cabeceras CORS donde 'Access-Control-Allow-Origin' se establece dinámicamente desde una variable de entorno ('process.env.CORS_ORIGIN'), y 'Access-Control-Allow-Credentials' se fija a 'true'. Esta com |
| `malreal_pypi_compromised_lib_mflux-streamlit_6` | rojo (min. 70) | verde (4) | ninguna | El nuevo fichero `main.py` es un simple wrapper para ejecutar una aplicación Streamlit local (`app.py`) usando `subprocess.run()`, sin llamadas de red, ejecución de código externo, exfiltración de datos o cambios en depe |
| `malreal_npm_compromised_lib__asyncapi_protobuf-schema-parser_150` | amarillo/rojo (min. 35) | verde (4) | ninguna | El cambio añade un nuevo módulo JavaScript que convierte esquemas Protocol Buffer a esquemas JSON, sin evidencia de ejecución de código externo arbitrario, exfiltración de datos o interacción con el sistema de archivos m |
| `malreal_npm_compromised_lib__tallyui_storage-sqlite_218` | rojo (min. 55) | verde (4) | ninguna | El cambio introduce un nuevo fichero de test de integración que verifica la funcionalidad de una base de datos local (RxDB con SQLite en memoria), sin llamadas de red, ejecución de código externo ni modificaciones a scri |
| `malreal_npm_malicious_intent_jstoauto_26` | rojo (min. 55) | verde (24) | ninguna | El fichero nuevo contiene código utilitario para una librería de logging (aparentemente `pino`), sin cadenas ofuscadas, llamadas de red sospechosas, o construcciones que permitan la ejecución remota de código. |
| `malreal_pypi_compromised_lib_lightning_5` | rojo (min. 55) | verde (4) | ninguna | El nuevo fichero Python implementa un lanzador de procesos para aplicaciones distribuidas, usando `subprocess.Popen` para replicar el script actual con diferentes variables de entorno para cada rango local, y no contiene |
