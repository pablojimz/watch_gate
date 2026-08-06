# Informe de validación — suite de aceptación (spec §14)

Generado automáticamente el 2026-08-06 10:38 UTC ejecutando `tests/integration/generate_validation_report.py` contra la API real de Gemini. No editar a mano -- regenerar con ese comando para que refleje el código actual. Resultados en bruto de cada caso en `docs/validation_report_raw.json`.

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
| `real_pallets_jinja_2105` | verde/amarillo (min. 0) | rojo (70) | backdoor | El cambio elimina por completo el job `provenance` y el paso de `generate hash` en el workflow `.github/workflows/publish.yaml`. Esto desactiva la generación de SLSA provenance, eliminando una capa crítica de seguridad q |
| `false_positive_candidate` | amarillo (min. 20) | verde (7) | ninguna | Aunque se introduce la función 'eval()', el código la utiliza con un control estricto del namespace y, crucialmente, con '__builtins__': {} para prevenir el acceso a funciones peligrosas, mitigando el riesgo de ejecución |
| `malreal_npm_compromised_lib_graphql-sequelize-teselagen_14` | rojo (min. 70) | verde (4) | ninguna | El cambio introduce un fichero nuevo con funciones estándar de codificación y decodificación base64, que no contienen lógica maliciosa, ofuscación, ni interacciones de red por sí mismas. |
| `malreal_npm_compromised_lib_tvi-cli_55` | rojo (min. 70) | amarillo (58) | backdoor | El nuevo middleware establece una política CORS dinámica para todas las rutas (`/:path*`), usando `process.env.CORS_ORIGIN` para el origen permitido y habilitando `Access-Control-Allow-Credentials: true`. Esto introduce  |
| `malreal_pypi_compromised_lib_mflux-streamlit_6` | rojo (min. 70) | verde (4) | ninguna | El cambio introduce un nuevo fichero 'main.py' que funciona como un wrapper para ejecutar una aplicación Streamlit ('app.py') en el mismo directorio, sin lógica sospechosa, llamadas de red ni manipulación de dependencias |
| `malreal_pypi_compromised_lib_xinference_11` | amarillo/rojo (min. 35) | verde (4) | ninguna | El cambio añade un nuevo fichero para una interfaz de chat que maneja salida de audio, incluyendo el uso de tempfile.NamedTemporaryFile para escribir datos de audio decodificados en base64. Esto es una funcionalidad legí |
| `malreal_npm_compromised_lib__tallyui_storage-sqlite_218` | rojo (min. 55) | verde (4) | ninguna | El cambio introduce un fichero de test de integración nuevo que usa un mock en memoria de SQLite para probar la funcionalidad de una base de datos, sin descargas externas, exfiltración de datos ni ofuscación. |
| `malreal_npm_malicious_intent_jstoauto_26` | rojo (min. 55) | verde (24) | ninguna | El archivo `tools.js` añadido contiene código JavaScript para utilidades de logging (probablemente parte de 'pino'), incluyendo serialización JSON, manejo de streams y formateo, sin ningún patrón de ofuscación, llamadas  |
| `malreal_pypi_compromised_lib_lightning_5` | rojo (min. 55) | verde (4) | ninguna | El nuevo fichero implementa un lanzador de procesos distribuidos, utilizando `subprocess.Popen` para ejecutar el propio script con diferentes `LOCAL_RANK`, y un observador de procesos para manejar las terminaciones, lo c |
