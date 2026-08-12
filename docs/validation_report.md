# Informe de validación — suite de aceptación (spec §14)

Generado automáticamente el 2026-08-12 10:21 UTC ejecutando `tests/integration/generate_validation_report.py` contra la API real de Gemini. No editar a mano -- regenerar con ese comando para que refleje el código actual. Resultados en bruto de cada caso en `docs/validation_report_raw.json`.

**Resultado global: 188/193 casos dentro de lo esperado (97%).**

> Score calculado con las 5 capas reales (`static` 0.25, `dependencies` 0.10, `vulnerabilities` 0.10, `reputation` 0.15, `semantic` 0.40) -- ver `tests/integration/pipeline_runner.py` para la nota histórica sobre por qué informes anteriores a este solo reflejaban `reputation`+`semantic`.

## Resumen por clase y dificultad

| Clase | Dificultad | N | OK | % OK |
|---|---|---:|---:|---:|
| benign | easy | 21 | 21 | 100% |
| benign | hard | 41 | 40 | 97% |
| benign | medium | 58 | 58 | 100% |
| canonico | - | 18 | 17 | 94% |
| malicious | easy | 21 | 21 | 100% |
| malicious | hard | 11 | 10 | 90% |
| malicious | medium | 23 | 21 | 91% |

## Resumen de casos maliciosos por naturaleza de amenaza detectada

Desglose de los casos `class=malicious` (mezclan ataques -- código malicioso/backdoors -- y vulnerabilidades -- dependencias con CVEs conocidos -- bajo una sola etiqueta) por la naturaleza que el propio sistema les asignó realmente (`threat_summary`, el mismo campo que ya usa el comentario de PR real). `-` significa que ninguna capa activa reportó un `Finding` con `threat_nature` -- típicamente un falso negativo total, no solo una naturaleza mal clasificada.

| Naturaleza detectada | N | OK | % OK |
|---|---:|---:|---:|
| ataque | 48 | 48 | 100% |
| vulnerabilidad | 5 | 4 | 80% |
| incertidumbre | 2 | 0 | 0% |

## Casos que divergen de lo esperado (5)

| Caso | Esperado | Obtenido | Naturaleza | Categoría | Justificación (semántica) |
|---|---|---|---|---|---|
| `real_pallets_jinja_2105` | verde/amarillo (min. 0) | rojo (70) | ataque | backdoor | El cambio elimina la generación de proveniencia SLSA (slsa-framework/slsa-github-generator) y el cálculo de hashes en .github/workflows/publish.yaml, desactivando la atestación criptográfica de integridad de las releases |
| `false_positive_candidate` | amarillo (min. 20) | rojo (70) | ataque | ninguna | Usa eval() para evaluar la expresión de usuario 'expr' en evaluate_formula(), confiando en que {'__builtins__': {}} aísla el entorno, lo cual permite ejecución remota de código (RCE) mediante la navegación por __globals_ |
| `malreal_pypi_malicious_intent_mirrorbot_10` | amarillo/rojo (min. 35) | verde (13) | incertidumbre | ninguna | El fichero direct_link_generator.py contiene funciones de generación y bypass de enlaces de descarga directa para múltiples servicios de almacenamiento, sin patrones de exfiltración, manipulación de dependencias ni ejecu |
| `malreal_npm_compromised_lib_posthog-node_2` | rojo (min. 55) | verde (25) | vulnerabilidad | ninguna | El fichero setup_bun.js descarga y ejecuta directamente el instalador oficial de Bun mediante 'curl -fsSL https://bun.sh/install \| bash' si Bun no está instalado, lo que constituye un patrón de ejecución de código remoto |
| `malreal_pypi_compromised_lib_lightning_5` | rojo (min. 55) | verde (4) | incertidumbre | ninguna | El cambio añade un script ejecutor en Python (start.py) que descarga el runtime Bun desde las releases oficiales de GitHub (oven-sh/bun) como alternativa si no está instalado y ejecuta router_runtime.js, sin exfiltración |
