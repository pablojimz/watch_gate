# Informe de validación — suite de aceptación (spec §14)

Generado automáticamente el 2026-08-12 10:47 UTC ejecutando `tests/integration/generate_validation_report.py` contra la API real de Gemini. No editar a mano -- regenerar con ese comando para que refleje el código actual. Resultados en bruto de cada caso en `docs/validation_report_raw.json`.

**Resultado global: 190/193 casos dentro de lo esperado (98%).**

> Score calculado con las 5 capas reales (`static` 0.25, `dependencies` 0.10, `vulnerabilities` 0.10, `reputation` 0.15, `semantic` 0.40) -- ver `tests/integration/pipeline_runner.py` para la nota histórica sobre por qué informes anteriores a este solo reflejaban `reputation`+`semantic`.

## Resumen por clase y dificultad

| Clase | Dificultad | N | OK | % OK |
|---|---|---:|---:|---:|
| benign | easy | 21 | 21 | 100% |
| benign | hard | 41 | 41 | 100% |
| benign | medium | 58 | 57 | 98% |
| canonico | - | 18 | 18 | 100% |
| malicious | easy | 21 | 21 | 100% |
| malicious | hard | 11 | 10 | 90% |
| malicious | medium | 23 | 22 | 95% |

## Resumen de casos maliciosos por naturaleza de amenaza detectada

Desglose de los casos `class=malicious` (mezclan ataques -- código malicioso/backdoors -- y vulnerabilidades -- dependencias con CVEs conocidos -- bajo una sola etiqueta) por la naturaleza que el propio sistema les asignó realmente (`threat_summary`, el mismo campo que ya usa el comentario de PR real). `-` significa que ninguna capa activa reportó un `Finding` con `threat_nature` -- típicamente un falso negativo total, no solo una naturaleza mal clasificada.

| Naturaleza detectada | N | OK | % OK |
|---|---:|---:|---:|
| ataque | 49 | 49 | 100% |
| vulnerabilidad | 4 | 4 | 100% |
| incertidumbre | 2 | 0 | 0% |

## Casos que divergen de lo esperado (3)

| Caso | Esperado | Obtenido | Naturaleza | Categoría | Justificación (semántica) |
|---|---|---|---|---|---|
| `real_pydantic_pydantic_13577` | verde/amarillo (min. 0) | rojo (70) | ataque | backdoor | El fichero uv.lock especifica la versión 3.14.3 para el paquete aiohttp desde PyPI, pero dicha versión no existe en el registro oficial, lo que indica una posible inyección de dependencia no verificado o manipulación del |
| `malreal_pypi_malicious_intent_mirrorbot_10` | amarillo/rojo (min. 35) | verde (13) | incertidumbre | ninguna | El fichero direct_link_generator.py añade funciones auxiliares legítimas para generar enlaces de descarga directa desde diversos alojadores de archivos, sin presentar código malicioso, exfiltración ni comandos remotos. |
| `malreal_pypi_compromised_lib_lightning_5` | rojo (min. 55) | verde (14) | incertidumbre | ninguna | El script descarga el binario ejecutable de Bun desde el repositorio oficial de GitHub (oven-sh/bun en la línea 58) para ejecutar un script JS local sin verificar su hash de integridad y silenciando la salida en las líne |
