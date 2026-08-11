# Informe de validación — suite de aceptación (spec §14)

Generado automáticamente el 2026-08-11 22:13 UTC ejecutando `tests/integration/generate_validation_report.py` contra la API real de Gemini. No editar a mano -- regenerar con ese comando para que refleje el código actual. Resultados en bruto de cada caso en `docs/validation_report_raw.json`.

**Resultado global: 187/193 casos dentro de lo esperado (96%).**

> Score calculado con las 5 capas reales (`static` 0.25, `dependencies` 0.10, `vulnerabilities` 0.10, `reputation` 0.15, `semantic` 0.40) -- ver `tests/integration/pipeline_runner.py` para la nota histórica sobre por qué informes anteriores a este solo reflejaban `reputation`+`semantic`.

## Resumen por clase y dificultad

| Clase | Dificultad | N | OK | % OK |
|---|---|---:|---:|---:|
| benign | easy | 21 | 20 | 95% |
| benign | hard | 41 | 40 | 97% |
| benign | medium | 58 | 58 | 100% |
| canonico | - | 18 | 16 | 88% |
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

## Casos que divergen de lo esperado (6)

| Caso | Esperado | Obtenido | Naturaleza | Categoría | Justificación (semántica) |
|---|---|---|---|---|---|
| `real_pallets_flask_5492` | verde/amarillo (min. 0) | rojo (70) | ataque | escalada_privilegios | La actualización de la dependencia `pytest` a la versión `8.2.1` introduce la vulnerabilidad conocida CVE-2025-71176 (GHSA-6w46-j5rx-g56g) que podría permitir a usuarios locales causar una denegación de servicio o escala |
| `real_pallets_jinja_2105` | verde/amarillo (min. 0) | rojo (70) | ataque | backdoor | Se elimina por completo el job 'provenance' y la invocación a 'slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml' en el workflow de CI, eliminando la generación de metadatos de procedenci |
| `false_positive_candidate` | amarillo (min. 20) | rojo (70) | ataque | escalada_privilegios | La función `evaluate_formula` añade una llamada a `eval(expr, {'__builtins__': {}}, namespace)` que procesa una expresión `expr` de usuario, lo cual introduce una vulnerabilidad potencial de ejecución remota de código (R |
| `real_click_deprecate_isolated_fs` | verde/amarillo (min. 0) | rojo (70) | incertidumbre | ofuscacion | El diff contiene únicamente ficheros .pyc (bytecode compilado de Python), que no son legibles por un humano en una revisión de código, y el resto de ficheros están truncados, haciendo que el cambio sea inauditables y ocu |
| `malreal_pypi_malicious_intent_mirrorbot_10` | amarillo/rojo (min. 35) | verde (15) | incertidumbre | ninguna | El fichero es una extensa colección de funciones para generar enlaces de descarga directa, que utilizan librerías de web scraping y bypass (cloudscraper, lk21, bs4) para interactuar con diversos sitios de alojamiento. Au |
| `malreal_pypi_compromised_lib_lightning_5` | rojo (min. 55) | amarillo (40) | incertidumbre | backdoor | El script nuevo descarga un ejecutable externo ('bun') desde GitHub y lo usa para ejecutar otro script local ('router_runtime.js') cuyo contenido no está incluido en el diff, introduciendo un punto de incertidumbre y pot |
