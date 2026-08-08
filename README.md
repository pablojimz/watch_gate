# WatchGate

Sistema de *scoring* de riesgo para la revisión automatizada de *pull requests* en pipelines CI/CD.

Proyecto presentado a los **Premios de la Cátedra de Ciberseguridad a la Innovación en Ciberseguridad e Inteligencia Artificial** (Universidad de Málaga). Memoria completa en [`docs/WatchGate_memoria.pdf`](docs/WatchGate_memoria.pdf) y especificación de construcción módulo a módulo en [`docs/WatchGate_spec_implementacion_IA.md`](docs/WatchGate_spec_implementacion_IA.md) — es la referencia autoritativa para implementar cada fichero (interfaz exacta, algoritmo, casos límite y test de aceptación). Reparto de tareas del equipo en [`docs/planificacion/plan_tareas_equipo.md`](docs/planificacion/plan_tareas_equipo.md).

## Equipo

- Javier Martín Jurado — capa semántica y de reputación
- Pablo Ayllón García — núcleo, orquestador, agregador y CLI
- Pablo Jiménez Castro — capa estática/dependencias y dashboard

*(Reparto de líneas actualizado respecto a la memoria original — ver [`docs/planificacion/plan_tareas_equipo.md`](docs/planificacion/plan_tareas_equipo.md) para el detalle.)*

## El problema

Los ataques a la cadena de suministro de software a través de *pull requests* (o mecanismos equivalentes: adopción de paquetes, scripts de compilación) son una amenaza creciente, agravada por el uso de IA generativa para crear *payloads* adaptativos y difíciles de detectar (casos recientes: **Atomic Arch** contra el AUR, **XZ Utils**, **prt-scan**). La revisión humana, como única barrera, sufre fatiga del revisor, sesgo de confianza hacia colaboradores habituales y dificultad para detectar intención maliciosa disimulada en cambios que parecen legítimos.

## La solución

WatchGate evalúa cada propuesta de código combinando cuatro señales independientes en una puntuación ponderada de 0 a 100, con desglose explicado por capa:

> **Nota sobre el ciclo de vida de los cambios (`git push` vs. *Pull Request*):**
> Cuando un desarrollador o colaborador envía cambios mediante `git push` a su rama o *fork*, los *commits* quedan subidos pero aislados. La amenaza a la cadena de suministro se concreta cuando se abre o actualiza un **Pull Request (PR)** o *Merge Request* para fusionar esos cambios en la rama principal (`main`). WatchGate intercepta la PR y evalúa el *diff* de ese *push* **antes de que sea aceptado y mergeado** en el servidor de producción. En entornos corporativos con Git interno, WatchGate también puede actuar directamente sobre el comando `git push` mediante un *hook* `pre-receive`.

| Capa | Qué mide | Técnica |
|---|---|---|
| **Estática** | Patrones de código peligrosos (`eval`, `exec`, ofuscación, escalada de privilegios) | Semgrep / YARA |
| **Dependencias** | Paquetes nuevos/modificados, *typosquatting*, CVEs conocidas | OSV, avisos de npm/PyPI |
| **Reputación** | Antigüedad e historial del autor vs. identidad declarada (nombre/correo) | API GitHub/GitLab |
| **Semántica (LLM)** | Intención real del cambio, con independencia de la reputación aparente | Prompting estructurado + RAG local |

El resultado se traduce en un semáforo de riesgo (verde/amarillo/rojo) publicado como comentario en el PR y como *check* de CI, con bloqueo de *merge* configurable.

```
[AMARILLO] WatchGate: Riesgo medio (47/100)

  Estática        20/100  (peso 0.25)
  Dependencias     10/100  (peso 0.20)
  Reputación       40/100  (peso 0.15)
  Semántica (LLM)  85/100  (peso 0.40)

Justificación (capa semántica):
  "El cambio añade una llamada de red a un dominio externo no
   declarado en la documentación del proyecto, activada durante
   el proceso de build."

-> Se recomienda revisión humana recomendada antes de mergear.
```

## Arquitectura

Núcleo agnóstico de plataforma + adaptadores finos (GitHub Actions, GitLab CI, hook `pre-receive` de un Git interno) + orquestador determinista + cuatro capas de análisis en paralelo + agregador de *scoring* + dashboard de postura de seguridad. Cada capa es un módulo independiente con la misma interfaz de entrada (`diff` + metadatos normalizados) y salida (`{ risk_score: 0-100, justification: string }`), lo que permite activar/desactivar capas por proyecto y sustituir componentes (p. ej. el proveedor de LLM) sin tocar el resto.

Detalle completo de la arquitectura (A.0–A.4), formato de salida, fórmula de *scoring* y control de coste de tokens: ver el **Anexo técnico** de la memoria.

## Estructura del repositorio

```
watch_gate/
├── pyproject.toml
├── Makefile
├── .watchgate.yml.example
├── watchgate/                          # Paquete Python instalable
│   ├── cli.py                          # Entrypoint CLI (`watchgate analyze` / `watchgate rag reindex`)
│   ├── config.py                       # Carga de configuración .watchgate.yml + variables de entorno
│   ├── core/                           # A.0 Núcleo agnóstico de plataforma (sin red, sin adapters/dashboard)
│   │   ├── diffparser.py               # Extracción determinista de diffs con GitPython
│   │   ├── models.py                   # Contratos Pydantic de datos
│   │   ├── layers/                     # A.3 Capas de análisis
│   │   │   ├── base.py                 #   Interfaz común + LAYER_REGISTRY
│   │   │   ├── static_layer.py         #   3a Estática (Semgrep/YARA)
│   │   │   ├── deps_layer.py           #   3b Dependencias (OSV, typosquatting)
│   │   │   ├── reputation_layer.py     #   3c Reputación del autor
│   │   │   └── _semantic/              #   3d Semántica (prompting, tools, client, layer)
│   │   ├── rag/                        # Sistema RAG local sobre ChromaDB (indexer, retriever, feedback)
│   │   ├── orchestrator.py             # A.1 Orquestador determinista concurrente multihilo
│   │   ├── aggregator.py               # A.2 Agregador de scoring y calculador de semáforo
│   │   ├── comment_template.py         # Renderizado Jinja2 del comentario Markdown de PR
│   │   ├── cost_control.py             # A.3.3 Control de coste de tokens y caché SQLite
│   │   └── shortcircuit.py             # A.3.4 Cortocircuito determinista para optimizar LLM
│   ├── adapters/github_action/         # A.0.1 Adaptador de referencia para GitHub Actions
│   └── dashboard/                       # A.4 Dashboard de postura de seguridad
│       ├── backend/
│       └── frontend/
├── rules/{semgrep,yara}/                 # Reglas de la capa estática
├── datasets/{few_shot,typosquat_reference}/
├── tests/                              # Pruebas unitarias e integradas
├── docs/                                  # Memoria, spec de implementación, plan de tareas
└── .github/workflows/watchgate.yml       # Workflow de referencia (GitHub Action)
```

## Uso de la CLI (`watchgate`)

Manual completo de la CLI disponible en [`docs/manual_cli.md`](docs/manual_cli.md).

### Instalación en desarrollo
```bash
pip install -e .
# O usando el entorno local:
.env/bin/pip install -e .
```

### Comandos y Modos de Uso

#### 1. Analizar un diff (`watchgate analyze`)
Realiza el análisis de riesgo entre dos commits, ramas o recibiendo el parche por la entrada estándar:

```bash
# Salida en formato comentario Markdown / Rich TTY interactivo
watchgate analyze --base main --head mi-rama

# Ingesta por pipeline Unix (stdin)
git diff main..HEAD | watchgate analyze --diff-stdin

# Exportación en estándar SARIF v2.1.0 para GitHub Code Scanning
watchgate analyze --base HEAD~1 --head HEAD --format sarif --output results.sarif

# Exportación en formato JSON crudo
watchgate analyze --base HEAD~1 --head HEAD --format json

# Anotaciones de GitHub Actions (::error:: / ::warning::)
watchgate analyze --base HEAD~1 --head HEAD --github-annotations

# Overrides dinámicos de pesos y umbrales al vuelo
watchgate analyze --base main --head dev --weight static=0.35 --weight semantic=0.35 --threshold red=80
```

**Parámetros opcionales:**
- `--base`: Commit o ref base (default: `main`, o `-` para `stdin`).
- `--head`: Commit o ref head (default: `HEAD`).
- `--diff-stdin`: Lee el parche unificado directamente desde `sys.stdin` (búfer máx 10 MB).
- `--repo-path`: Ruta al repo local (default: `.`).
- `--config`: Ruta a `.watchgate.yml` (default: `.watchgate.yml`).
- `--format`: Formato de salida (`comment`, `json`, `sarif`; default: `comment`).
- `--github-annotations`: Emite comandos de flujo de trabajo de GitHub Actions (`::error::` / `::warning::`).
- `--weight`: Override dinámico de peso de capa (ej: `--weight static=0.35`).
- `--threshold`: Override dinámico de umbral (ej: `--threshold red=80`).
- `--pr-id` / `--repo`: Identificador de PR y nombre de repositorio.
- `--author-login` / `--author-email`: Identidad declarada del autor.
- `-v` / `--verbose` / `--debug` / `-q` (`--quiet`): Niveles de diagnóstico y logs.
- `--output`: Archivo de destino para guardar el informe.

**Códigos de Salida (Exit Codes):**
- `0`: Análisis completado sin bloqueos (VERDE / AMARILLO).
- `1`: Bloqueo por política activa (Semáforo ROJO y `block_on_red: true`).
- `2`: Error de configuración, banderas inválidas o sintaxis de diff corrupta.
- `3`: Fallo de infraestructura o API externa.

#### 2. Reindexar el corpus RAG (`watchgate rag reindex`)
Reconstruye el índice vectorial ChromaDB con el corpus local de patrones de ataque:

```bash
watchgate rag reindex
```

### Configuración de Proveedores LLM

La capa semántica soporta múltiples proveedores configurables mediante variables de entorno:

* **Anthropic (por defecto):**
  ```bash
  export ANTHROPIC_API_KEY="sk-ant-..."
  ```
* **Google Gemini:**
  ```bash
  export WATCHGATE_LLM_PROVIDER="gemini"
  export GEMINI_API_KEY="AIzaSy..."
  ```
* **LLM Local (Ollama / vLLM / llama.cpp):**
  ```bash
  export WATCHGATE_LLM_PROVIDER="local"
  export WATCHGATE_LLM_BASE_URL="http://localhost:11434/v1"  # Servidor Ollama
  export WATCHGATE_LLM_MODEL="llama3.1"
  ```

## Configuración del proyecto (`.watchgate.yml`)

Pesos y umbrales de semáforo configurables por repositorio en `.watchgate.yml` (ver [`.watchgate.yml.example`](.watchgate.yml.example)):

```yaml
weights:    { static: 0.25, dependencies: 0.20, reputation: 0.15, semantic: 0.40 }
thresholds: { yellow: 40, red: 70 }
block_on_red: true
shortcircuit_enabled: false
```

## Despliegue

Guía completa (checklist de producción, variables de entorno, limitaciones conocidas) en [`docs/despliegue.md`](docs/despliegue.md). Arranque rápido del stack completo (Engine API + Dashboard backend/frontend + Postgres) con Docker Compose:

```bash
cp .env.example .env   # rellena al menos WATCHGATE_LLM_API_KEY
docker compose up --build
```

## Pruebas y Calidad de Código

Para ejecutar la batería de pruebas y las herramientas de análisis estático:

```bash
# Ejecutar los tests unitarios
pytest

# Comprobar el formateo y linter
ruff check .

# Verificación de tipos estáticos
mypy watchgate
```

## Estado del desarrollo

Arquitectura y spec de implementación cerradas (`docs/WatchGate_spec_implementacion_IA.md`). Estado de tareas (`docs/planificacion/plan_tareas_equipo.md`):

- [x] Fase 0 — contratos de datos (`core/models.py`) + interfaz común de capas y registro (`core/layers/base.py`, A.0.0)
- [x] Parser de diffs (`core/diffparser.py`, A.0)
- [x] Capa de reputación (`reputation_layer.py`)
- [x] Capa semántica (`_semantic/` + RAG local)
- [x] Control de coste de tokens y caché (`cost_control.py`, A.3.3)
- [x] Orquestador determinista + agregador de *scoring* (`orchestrator.py`, `aggregator.py`, `comment_template.py`)
- [x] Cortocircuito de extremo (`shortcircuit.py`, A.3.4)
- [x] Interfaz de Línea de Comandos CLI (`cli.py`)
- [x] Capa estática (Semgrep/YARA) — Pablo Jiménez Castro
- [x] Capa de dependencias (OSV, typosquatting) — Pablo Jiménez Castro
- [x] Adaptador de GitHub Action de referencia (`adapters/github_action/`), incluida la persistencia opcional en el dashboard (paso 8 de la spec §12) y la aplicación opcional de la configuración del dashboard (pesos/umbrales/capas/política/presupuesto de LLM) por repo antes de analizar
- [x] Dashboard de postura de seguridad (`dashboard/`) — Pablo Jiménez Castro
- [x] Validación contra el conjunto de casos de prueba (191 casos, 95% dentro de lo esperado — `docs/validation_report.md`)

Pendiente antes de un despliegue real: publicar el paquete en PyPI (`pip install watchgate` hoy solo funciona instalando desde el propio checkout, ver `.github/workflows/watchgate.yml`).

## Referencias

- Wiz Research, *prt-scan*: [AI-Powered GitHub Actions Supply Chain Attack](https://www.wiz.io/blog/six-accounts-one-actor-inside-the-prt-scan-supply-chain-campaign)
- StepSecurity, [400+ AUR Packages Hijacked: the "Atomic Arch" Campaign](https://www.stepsecurity.io/blog/400-aur-packages-hijacked-atomic-arch-campaign)
- Datadog Security Labs, [BewAIre: detección de código malicioso en PRs con LLMs](https://www.datadoghq.com/blog/engineering/scaling-malicious-code-detection/)
- [GuardDog](https://github.com/DataDog/guarddog) · [Socket.dev](https://docs.socket.dev/docs/socket-for-github) · [Semgrep](https://semgrep.dev) · [OSV](https://osv.dev) · [GitHub Advisory Database](https://github.com/advisories)
