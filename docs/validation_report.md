# Informe de validación — suite de aceptación (spec §14)

Generado automáticamente el 2026-08-05 14:12 UTC ejecutando `tests/integration/generate_validation_report.py` contra la API real de Gemini. No editar a mano -- regenerar con ese comando para que refleje el código actual. Resultados en bruto de cada caso en `docs/validation_report_raw.json`.

**Resultado global: 172/191 casos dentro de lo esperado (90%).**

> `static_layer.py`/`deps_layer.py` (Línea 3) siguen sin implementar: el score de esta suite es la media ponderada renormalizada de `reputation` (0.15) + `semantic` (0.40) únicamente, no las 4 capas de la memoria §8.

## Resumen por clase y dificultad

| Clase | Dificultad | N | OK | % OK |
|---|---|---:|---:|---:|
| benign | easy | 21 | 21 | 100% |
| benign | hard | 41 | 41 | 100% |
| benign | medium | 58 | 58 | 100% |
| canonico | - | 18 | 18 | 100% |
| malicious | easy | 21 | 18 | 85% |
| malicious | hard | 10 | 2 | 20% |
| malicious | medium | 22 | 14 | 63% |

## Casos que divergen de lo esperado (19)

| Caso | Esperado | Obtenido | Categoría | Justificación (semántica) |
|---|---|---|---|---|
| `malreal_npm_compromised_lib_graphql-sequelize-teselagen_14` | rojo (min. 70) | verde (4) | ninguna | El cambio añade un fichero de utilidad para codificación y decodificación base64 estándar en Node.js, sin indicios de código malicioso, ofuscación o llamadas externas. |
| `malreal_npm_compromised_lib_tvi-cli_55` | rojo (min. 70) | amarillo (44) | exfiltracion | El nuevo middleware configura dinámicamente el encabezado 'Access-Control-Allow-Origin' a partir de una variable de entorno ('process.env.CORS_ORIGIN') mientras establece 'Access-Control-Allow-Credentials' a 'true', lo q |
| `malreal_pypi_compromised_lib_mflux-streamlit_6` | rojo (min. 70) | verde (4) | ninguna | El cambio introduce un nuevo script `main.py` que simplemente lanza una aplicación Streamlit local (`app.py`) usando `subprocess.run`, sin llamadas externas, nuevas dependencias ni cambios en la configuración de build. |
| `malreal_npm_compromised_lib__asyncapi_protobuf-schema-parser_150` | rojo (min. 35) | verde (4) | ninguna | El cambio añade un nuevo módulo JavaScript para convertir esquemas Protocol Buffers a JSON Schema, utilizando la librería protobufjs, y no muestra indicios de actividad maliciosa como exfiltración, puertas traseras o eje |
| `malreal_npm_malicious_intent_nit-quotation-service-core-lib_34` | rojo (min. 35) | verde (24) | ninguna | El diff no muestra patrones maliciosos obvios. El fichero .gitkeep_base no contiene cambios significativos y helpers.js, aunque grande, no ha sido detectado con patrones maliciosos por el análisis estático. |
| `malreal_pypi_compromised_lib_litellm_8` | rojo (min. 35) | verde (7) | ninguna | Se añaden 9498 líneas a `utils.py` sin que el análisis estático detecte patrones maliciosos, y 0 líneas a `.gitkeep_base`. |
| `malreal_pypi_compromised_lib_telnyx_2` | rojo (min. 35) | verde (0) | ninguna | El diff solo indica que se han añadido líneas a '_client.py' sin mostrar su contenido real, impidiendo cualquier análisis de seguridad del código. |
| `malreal_pypi_compromised_lib_telnyx_4` | rojo (min. 35) | verde (4) | ninguna | Se han añadido 7828 líneas al fichero _client.py y 0 al fichero .gitkeep_base. El análisis estático no ha detectado ningún patrón de código malicioso en las líneas añadidas de ninguno de los dos ficheros. |
| `malreal_pypi_compromised_lib_xinference_11` | rojo (min. 35) | verde (4) | ninguna | El diff no presenta patrones de cambios maliciosos; solo se indica la adición de líneas a un fichero Python sin patrones detectados por análisis estático y un fichero .gitkeep sin cambios. |
| `malreal_pypi_malicious_intent_mirrorbot_10` | rojo (min. 35) | verde (24) | ninguna | Se añade un nuevo fichero .py de 811 líneas y un fichero .gitkeep_base sin patrones maliciosos detectados por el análisis estático en ninguna de las nuevas líneas. |
| `malreal_pypi_malicious_intent_mysqlloadup_7` | rojo (min. 35) | verde (24) | ninguna | El diff no muestra cambios ni patrones de código sospechosos en los ficheros .gitkeep_base ni __init__.py; ambos son convenciones estándar sin contenido malicioso. |
| `malreal_npm_compromised_lib__ensdomains_hardhat-toolbox-viem-extende_285` | rojo (min. 55) | amarillo (65) | backdoor | El script descarga y ejecuta código arbitrario de dominios externos ('bun.sh/install.ps1' vía PowerShell y 'bun.sh/install' vía curl \| bash), y luego procede a ejecutar un script local 'bun_environment.js' usando el bina |
| `malreal_npm_compromised_lib__ensdomains_subdomain-registrar_137` | rojo (min. 55) | amarillo (65) | backdoor | El script descarga y ejecuta directamente código externo desde 'https://bun.sh/install' (líneas 56-59), que puede cambiar arbitrariamente después de la revisión del PR, y luego intenta ejecutar un script local no incluid |
| `malreal_npm_compromised_lib__tallyui_storage-sqlite_218` | rojo (min. 55) | verde (4) | ninguna | El cambio consiste en añadir un nuevo fichero de test de integración para una base de datos RxDB con SQLite, que realiza operaciones CRUD estándar sin lógica sospechosa, llamadas de red o interacción con el sistema fuera |
| `malreal_npm_compromised_lib__voiceflow_fetch_97` | rojo (min. 55) | amarillo (65) | backdoor | El script descarga y ejecuta código directamente de 'bun.sh/install' (o 'bun.sh/install.ps1' en Windows) sin verificar su contenido, un patrón de 'curl \| bash' con alto riesgo de cadena de suministro. Además, al finaliza |
| `malreal_npm_compromised_lib_posthog-node_2` | rojo (min. 55) | amarillo (69) | backdoor | El nuevo script descarga y ejecuta código arbitrario (`curl ... \| bash` o `irm ... \| iex`) directamente desde un dominio externo durante la instalación, y posteriormente intenta ejecutar un script `bun_environment.js` qu |
| `malreal_npm_compromised_lib_undefsafe-typed_29` | rojo (min. 55) | amarillo (65) | backdoor | El nuevo script descarga y ejecuta código arbitrario de dominios externos (bun.sh/install) usando `curl \| bash` o `powershell \| iex`, lo cual es un patrón de alto riesgo para la inyección de código remoto y la creación d |
| `malreal_npm_malicious_intent_jstoauto_26` | rojo (min. 55) | verde (24) | ninguna | Se añade un nuevo archivo `tools.js` que contiene lógica para una librería de logging (serialización, formateo, manejo de streams de salida), sin patrones de ofuscación, exfiltración, ejecución de código remoto o cambios |
| `malreal_pypi_compromised_lib_lightning_5` | rojo (min. 55) | verde (7) | ninguna | El nuevo fichero es un lanzador de procesos distribuidos que usa 'subprocess.Popen' para re-ejecutar el mismo script en procesos hijos, estableciendo variables de entorno estándar para DDP; no descarga ni ejecuta código  |
