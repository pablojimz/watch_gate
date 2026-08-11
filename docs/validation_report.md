# Informe de validación — suite de aceptación (spec §14)

Generado automáticamente el 2026-08-11 15:13 UTC ejecutando `tests/integration/generate_validation_report.py` contra la API real de Gemini. No editar a mano -- regenerar con ese comando para que refleje el código actual. Resultados en bruto de cada caso en `docs/validation_report_raw.json`.

**Resultado global: 189/193 casos dentro de lo esperado (97%).**

> Score calculado con las 5 capas reales (`static` 0.25, `dependencies` 0.10, `vulnerabilities` 0.10, `reputation` 0.15, `semantic` 0.40) -- ver `tests/integration/pipeline_runner.py` para la nota histórica sobre por qué informes anteriores a este solo reflejaban `reputation`+`semantic`.

## Resumen por clase y dificultad

| Clase | Dificultad | N | OK | % OK |
|---|---|---:|---:|---:|
| benign | easy | 21 | 21 | 100% |
| benign | hard | 41 | 40 | 97% |
| benign | medium | 58 | 58 | 100% |
| canonico | - | 18 | 17 | 94% |
| malicious | easy | 21 | 20 | 95% |
| malicious | hard | 11 | 10 | 90% |
| malicious | medium | 23 | 23 | 100% |

## Resumen de casos maliciosos por naturaleza de amenaza detectada

Desglose de los casos `class=malicious` (mezclan ataques -- código malicioso/backdoors -- y vulnerabilidades -- dependencias con CVEs conocidos -- bajo una sola etiqueta) por la naturaleza que el propio sistema les asignó realmente (`threat_summary`, el mismo campo que ya usa el comentario de PR real). `-` significa que ninguna capa activa reportó un `Finding` con `threat_nature` -- típicamente un falso negativo total, no solo una naturaleza mal clasificada.

| Naturaleza detectada | N | OK | % OK |
|---|---:|---:|---:|
| ataque | 49 | 49 | 100% |
| vulnerabilidad | 5 | 3 | 60% |
| incertidumbre | 1 | 1 | 100% |

## Casos que divergen de lo esperado (4)

| Caso | Esperado | Obtenido | Naturaleza | Categoría | Justificación (semántica) |
|---|---|---|---|---|---|
| `real_pallets_jinja_2098` | verde/amarillo (min. 0) | rojo (70) | vulnerabilidad | ofuscacion | El método `__getattr__` añadido en `src/jinja2/__init__.py` hace que, al acceder al atributo `__version__`, este devuelva la versión de 'werkzeug' en lugar de la versión real de Jinja2, misrepresentando la identidad del  |
| `false_positive_candidate` | amarillo (min. 20) | rojo (70) | ataque | escalada_privilegios | La función 'evaluate_formula' utiliza 'eval()' con un namespace que incluye objetos de 'math' (p. ej. 'sqrt'), los cuales permiten acceder a los 'builtins' originales a través de sus '__globals__', eludiendo la restricci |
| `malreal_npm_compromised_lib_tvi-cli_55` | rojo (min. 70) | verde (4) | vulnerabilidad | ninguna | El cambio añade un middleware de Next.js que configura cabeceras CORS utilizando una variable de entorno para 'Access-Control-Allow-Origin'. Aunque el uso de una variable de entorno es una buena práctica, una configuraci |
| `malreal_pypi_malicious_intent_mirrorbot_10` | amarillo/rojo (min. 35) | verde (39) | vulnerabilidad | backdoor | La función `terabox` carga cookies de sesión desde el fichero `terabox.txt` (líneas 806-808) sin mecanismos de seguridad o validación de integridad para dicho fichero, lo que podría permitir la inyección de cookies malic |
