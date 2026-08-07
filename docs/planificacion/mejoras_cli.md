# Plan de Implementación: Mejoras y Modernización de la CLI de WatchGate (Versión Auditada)

## Metadatos

- **Autor / Responsable**: Equipo de Desarrollo e Infraestructura de WatchGate (Pablo Ayllón García)
- **Estado**: Especificación Técnica Auditada / Aprobada para Producción
- **Fecha de creación**: 2026-08-07
- **Última actualización**: 2026-08-07
- **Objetivo**: Especificar la arquitectura, módulos, contratos de datos, salvaguardas de producción y plan de tareas para transformar la CLI de WatchGate (`watchgate`) en una herramienta de nivel de producción con excelente experiencia de desarrollador (DX/UX), soporte nativo para pipelines Unix (`stdin`), integración avanzada en CI/CD (SARIF v2.1.0, GitHub Annotations), overrides dinámicos y diagnósticos granulares.

---

# 1. Motivación y Estado Actual vs. Estado Objetivo

### Estado Actual (`watchgate/cli.py`):
- Muestra salidas en texto plano Markdown o JSON crudo mediante `print()`.
- Requiere obligatoriamente un repositorio Git local en disco (`--repo-path`) y referencias físicas (`--base` / `--head`).
- No permite ajustar pesos ni umbrales sin editar el archivo `.watchgate.yml`.
- Los códigos de salida se limitan a `0` (éxito/sin bloqueo) y `1` (bloqueo por semáforo rojo) o `2` (error básico de parseo).
- No soporta integración directa con GitHub Code Scanning (SARIF) ni anotaciones visuales en diffs de GitHub Actions.

### Estado Objetivo:
- **DX Interactiva Avanzada:** Formateo `rich` en terminales TTY (paneles de colores, tablas con desglose por capa y spinners de carga en ejecuciones paralelas).
- **Flexibilidad de Ingesta (Unix Pipelines):** Soporte para recibir diffs directamente desde la entrada estándar (`git diff | watchgate analyze --diff-stdin`), protegido con límite de tamaño de búfer.
- **Overrides al Vuelo:** Alterar pesos de capas y umbrales de riesgo mediante banderas CLI sin modificar archivos de configuración, con re-normalización automática.
- **Interoperabilidad CI/CD:** Generación de archivos SARIF v2.1.0 con rutas relativas estandarizadas e impresión de comandos de workflow de GitHub Actions (`::error::`, `::warning::`) dirigidos limpiamente a `stderr` si hay salida estructurada.
- **Diagnóstico y Control de Logs:** Niveles de verbosidad granulares (`--verbose`, `--debug`, `--quiet`).
- **Códigos de Salida Estandarizados:** Mapeo preciso de fallos (0: OK, 1: Bloqueo de Política, 2: Error de Configuración/Args/Diff, 3: Fallo de Infraestructura/API).

---

# 2. Salvaguardas Críticas de Producción (Revisión Senior)

Tras la auditoría técnica externa, se fijan **4 reglas de arquitectura obligatorias**:

### Rule 1: Aislamiento de `stdout` para Anotaciones de CI/CD
Las anotaciones de flujo de trabajo (`--github-annotations`) **se imprimirán exclusivamente en `sys.stderr`** cuando el formato principal de salida sea `--format json` o `--format sarif`. De este modo se evita la corrupción del archivo JSON/SARIF en `sys.stdout` que rompería herramientas como `jq` o la ingesta de GitHub Code Scanning.

### Rule 2: Ingesta `stdin` Segura y No Bloqueante (Límite 10 MB)
1. Antes de invocar `sys.stdin.read()`, se verificará `sys.stdin.isatty()`. Si la opción `--diff-stdin` está activa pero `stdin` es interactivo (sin datos canalizados por pipe), se abortará inmediatamente con mensaje de error y **Exit Code 2**.
2. Se impondrá un límite máximo de lectura de **10 MB** (10,485,760 bytes). Parches que excedan este tamaño abortarán con un error explicativo para prevenir ataques DoS por agotamiento de RAM (*OOM Killer*).

### Rule 3: Normalización Estricta de Rutas en SARIF v2.1.0
El formateador `watchgate/formatters/sarif.py` limpiará todas las rutas de los hallazgos (`Finding.file_path`):
- Eliminará prefijos absolutos de máquina (ej. `/home/user/project/...` -> `src/main.py`).
- Eliminará secuencias de navegación como `./` y `../`.
- Esto garantiza que GitHub Code Scanning acepte el archivo SARIF sin rechazarlo por rutas fuera de workspace.

### Rule 4: Fallback Elegante para la Capa Semántica (LLM) en SARIF
Los LLM no garantizan la precisión de números de línea exactos. Los hallazgos de la capa semántica que no traigan un número de línea estructurado se asignarán en SARIF a nivel de archivo (`line: 1` o sin bloque `region`), impidiendo que el LLM alucine ubicaciones falsas.

---

# 3. Contratos de Datos y Extensión de Modelos

### A. Estructura de Hallazgos en `LayerResult` (`watchgate/core/models.py`)
Para alimentar SARIF y GitHub Annotations de forma fuertemente tipada:

```python
class Finding(BaseModel):
    file_path: str
    line: int | None = None
    end_line: int | None = None
    rule_id: str
    message: str
    severity: str = "warning"  # "error", "warning", "info"

class LayerResult(BaseModel):
    layer_name: str
    risk_score: int = Field(ge=0, le=100)
    justification: str
    findings: list[Finding] = Field(default_factory=list)  # Hallazgos estructurados opcionales
    category: RiskCategory | None = None
    confidence: Confidence | None = None
    skipped: bool = False
    skip_reason: str | None = None
    tool_calls_made: int = 0
```

### B. Desacoplamiento de UI en el Orquestador (`watchgate/core/orchestrator.py`)
El orquestador no tendrá dependencias de `rich`. Aceptará un callback agnóstico y thread-safe:

```python
ProgressCallback = Callable[[str, str], None]  # (layer_name, status: "start" | "done" | "fail")

def run_analysis(
    diff: NormalizedDiff,
    metadata: dict[str, object],
    config: WatchGateConfig,
    layer_factories: dict[str, LayerFactory] | None = None,
    on_progress: ProgressCallback | None = None,
) -> AggregatedResult:
```

### C. Re-normalización Automática de Pesos (`watchgate/config.py`)
Si al aplicar `--weight layer=val` la suma $S = \sum w_i \neq 1.0$, la función `apply_cli_overrides` dividirá cada peso por $S$ ($w_i' = w_i / S$) y emitirá un log de tipo `WARNING`.

---

# 4. Arquitectura de Módulos Propuesta

```
watchgate/
├── cli.py                        # Entrypoint, subparsers, argparse, manejo de stdin y exit codes
├── config.py                     # Carga de config y overrides dinámicos (apply_cli_overrides)
└── formatters/                   # Módulo de formateo (Strategy Pattern)
    ├── __init__.py
    ├── console.py                # Renderizado interactivo TTY con 'rich' (paneles, tablas, badges)
    ├── github.py                 # Generación de GitHub Actions Workflow Commands (a stderr/stdout)
    └── sarif.py                  # Transformación de AggregatedResult/Findings a esquema SARIF 2.1.0
```

---

# 5. Especificación Detallada de Módulos

## 5.1 🖥️ Módulo 1: Experiencia de Usuario Terminal (DX / UX)
- **Renderizado TTY:** Cuando `sys.stdout.isatty()` sea `True` y `--format` sea `comment`:
  - **VERDE (< 40):** Panel verde `[PASS] RIESGO BAJO`.
  - **AMARILLO (40-69):** Panel amarillo `[WARN] RIESGO MEDIO`.
  - **ROJO (>= 70):** Panel rojo `[BLOCK] RIESGO ALTO`.
  - **Tabla por Capas:** *Capa*, *Puntuación*, *Peso*, *Contribución*, *Estado*, *Detalles*.
- **Manejo de Logs Concurrente:** Los spinners de `rich` se dibujarán en `stderr` y el logger redirigirá sus salidas a través del Handler de `rich` para evitar romper el renderizado.
- **Autocompletado:** Integración con `argcomplete` mediante `# PYTHON_ARGCOMPLETE_OK`.

## 5.2 🔀 Módulo 2: Ingesta de Diffs por Entrada Estándar (`stdin`)
- Activación mediante `--diff-stdin` o `--base -`.
- Lectura con búfer limitado a 10 MB.
- Metadatos por defecto en ejecuciones por `stdin`: `base_sha="STDIN_BASE"`, `head_sha="STDIN_HEAD"`, `repo="local/stdin"`.
- Asignación opcional mediante `--author-login`, `--author-email`.

## 5.3 🎯 Módulo 3: Overrides Dinámicos CLI
- Parámetros `--weight layer=val` y `--threshold level=val`.
- Validación de claves y re-normalización automática de la suma de pesos.

## 5.4 📊 Módulo 4: Formatos CI/CD (SARIF v2.1.0 y GitHub Annotations)
- **`watchgate/formatters/sarif.py`:** Convierte `AggregatedResult` y `Finding` en SARIF v2.1.0 con rutas relativas limpias.
- **`watchgate/formatters/github.py`:** Genera anotaciones `::error file=...::`. Redirigidas a `stderr` si `--format` es `json` o `sarif`.

## 5.5 🔍 Módulo 5: Control de Verbosidad
- `--quiet` / `-q`: Silencia `stderr`. Solo emite el informe final en `stdout`.
- `--verbose` / `-v`: Nivel `logging.INFO`.
- `--debug`: Nivel `logging.DEBUG`.

## 5.6 🛑 Módulo 6: Granularidad en Códigos de Salida (Exit Codes)

| Código | Categoría | Escenario de Disparo |
| :---: | :--- | :--- |
| **`0`** | **Éxito / Aprobado** | Análisis completado con éxito. Semáforo VERDE, AMARILLO o ROJO (con `block_on_red: false`). |
| **`1`** | **Bloqueo por Política** | Semáforo **ROJO** y regla `block_on_red: true` activa. |
| **`2`** | **Error de User / Config / Diff** | Configuración/argumentos inválidos, `stdin` sin datos, parche corrupto o >10MB. |
| **`3`** | **Error de Infraestructura / API** | Fallo crítico no recuperable de dependencias o red (ej. timeout de API obligatoria). |

---

# 6. Plan de Trabajo por Fases

```
├── Fase 1: Extensión de Contratos y Formateadores CI/CD
│   ├── Añadir 'rich' y 'argcomplete' a pyproject.toml
│   ├── Añadir modelo Finding a LayerResult en watchgate/core/models.py
│   ├── Crear paquete watchgate/formatters/
│   ├── Implementar watchgate/formatters/sarif.py (con normalización de rutas)
│   └── Implementar watchgate/formatters/github.py (con redirección a stderr cuando aplique)
│
├── Fase 2: Overrides de Configuración e Ingesta por Stdin
│   ├── Implementar apply_cli_overrides() en watchgate/config.py (con re-normalización)
│   ├── Añadir soporte --diff-stdin en watchgate/cli.py (con verificación isatty y límite 10MB)
│   └── Poblar findings en capas estáticas/dependencias
│
├── Fase 3: Callback de Orquestador, UX Rich y Shell Completion
│   ├── Añadir callback thread-safe on_progress en orchestrator.py
│   ├── Implementar watchgate/formatters/console.py con 'rich'
│   └── Activar autocompletado argcomplete en cli.py
│
├── Fase 4: Verbosidad, Diagnósticos y Exit Codes Granulares
│   ├── Configurar manejo de logs (--verbose, --debug, --quiet)
│   └── Refactorizar main() en cli.py para devolver códigos 0, 1, 2, 3
│
└── Fase 5: Suite de Pruebas Unitarias e Integradas
    ├── Escribir tests/test_formatters.py
    └── Escribir tests/test_cli.py
```

---

# 7. Estrategia de Verificación y Testing

1. **Pruebas de Formateadores (`tests/test_formatters.py`):**
   - Validar cumplimiento del esquema SARIF v2.1.0 y ausencia de rutas absolutas.
   - Validar emisión de comandos `::error::` y `::warning::` en `stderr`.
2. **Pruebas de Ingesta por Stdin (`tests/test_cli.py`):**
   - Probar parche estándar por `stdin` -> Exit code `0`.
   - Probar `stdin` sin datos (TTY) -> Exit code `2`.
   - Probar parche > 10 MB por `stdin` -> Exit code `2`.
3. **Pruebas de Overrides y Exit Codes (`tests/test_cli.py`):**
   - Probar re-normalización de pesos cuando la suma no es 1.0.
   - Validar códigos de retorno 0, 1, 2 y 3.
