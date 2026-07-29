# WatchGate

Sistema de *scoring* de riesgo para la revisión automatizada de *pull requests* en pipelines CI/CD.

Proyecto presentado a los **Premios de la Cátedra de Ciberseguridad a la Innovación en Ciberseguridad e Inteligencia Artificial** (Universidad de Málaga). Memoria completa en [`docs/WatchGate_memoria.pdf`](docs/WatchGate_memoria.pdf) y especificación de construcción módulo a módulo en [`docs/WatchGate_spec_implementacion_IA.md`](docs/WatchGate_spec_implementacion_IA.md) — es la referencia autoritativa para implementar cada fichero (interfaz exacta, algoritmo, casos límite y test de aceptación). Reparto de tareas del equipo en [`docs/plan_tareas_equipo.md`](docs/plan_tareas_equipo.md).

## Equipo

- Javier Martín Jurado — capa semántica y de reputación
- Pablo Ayllón García — núcleo, orquestador y agregador
- Pablo Jiménez Castro — capa estática/dependencias y dashboard

*(Reparto de líneas actualizado respecto a la memoria original — ver [`docs/plan_tareas_equipo.md`](docs/plan_tareas_equipo.md) para el detalle.)*

## El problema

Los ataques a la cadena de suministro de software a través de *pull requests* (o mecanismos equivalentes: adopción de paquetes, scripts de compilación) son una amenaza creciente, agravada por el uso de IA generativa para crear *payloads* adaptativos y difíciles de detectar (casos recientes: **Atomic Arch** contra el AUR, **XZ Utils**, **prt-scan**). La revisión humana, como única barrera, sufre fatiga del revisor, sesgo de confianza hacia colaboradores habituales y dificultad para detectar intención maliciosa disimulada en cambios que parecen legítimos.

## La solución

WatchGate evalúa cada PR combinando cuatro señales independientes en una puntuación ponderada de 0 a 100, con desglose explicado por capa:

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

-> Se recomienda revisión humana reforzada antes de fusionar.
```

## Arquitectura

Núcleo agnóstico de plataforma + adaptadores finos (GitHub Actions, GitLab CI, hook `pre-receive` de un Git interno) + orquestador determinista + cuatro capas de análisis en paralelo + agregador de *scoring* + dashboard de postura de seguridad. Cada capa es un módulo independiente con la misma interfaz de entrada (`diff` + metadatos normalizados) y salida (`{ risk_score: 0-100, justification: string }`), lo que permite activar/desactivar capas por proyecto y sustituir componentes (p. ej. el proveedor de LLM) sin tocar el resto.

Detalle completo de la arquitectura (A.0–A.4), formato de salida, fórmula de *scoring* y control de coste de tokens: ver el **Anexo técnico** de la memoria.

## Estructura del repositorio

Sigue exactamente el árbol de la especificación de implementación (`docs/WatchGate_spec_implementacion_IA.md`, §0). Cada módulo de `watchgate/` es de momento un *stub* (docstring apuntando a la sección de la spec que lo rige); la lógica se implementa siguiendo el reparto de `docs/plan_tareas_equipo.md`.

```
watch_gate/
├── pyproject.toml
├── Makefile
├── .watchgate.yml.example
├── watchgate/                          # paquete Python instalable
│   ├── cli.py
│   ├── config.py
│   ├── core/                           # A.0  Núcleo agnóstico de plataforma (sin red, sin adapters/dashboard)
│   │   ├── diffparser.py
│   │   ├── models.py                   # contratos de datos — base de todo lo demás
│   │   ├── layers/                     # A.3  Capas de análisis
│   │   │   ├── base.py                 #   Interfaz común + LAYER_REGISTRY (A.0.0)
│   │   │   ├── static_layer.py         #   3a Estática (Semgrep/YARA)
│   │   │   ├── deps_layer.py           #   3b Dependencias (OSV, typosquatting)
│   │   │   ├── reputation_layer.py     #   3c Reputación del autor
│   │   │   └── _semantic/              #   3d Semántica (prompting, tools, client, layer)
│   │   ├── rag/corpus/                 # Corpus local para la capa semántica
│   │   ├── orchestrator.py             # A.1  Orquestador determinista
│   │   ├── aggregator.py               # A.2  Agregador de scoring
│   │   ├── cost_control.py             # A.3.3 Control de coste de tokens
│   │   └── shortcircuit.py             # A.3.4 (objetivo ampliado)
│   ├── adapters/github_action/         # A.0.1 Adaptador de referencia
│   └── dashboard/                       # A.4  Dashboard de postura de seguridad
│       ├── backend/
│       └── frontend/
├── rules/{semgrep,yara}/                 # Reglas de la capa estática
├── datasets/{few_shot,typosquat_reference}/
├── tests/{unit,integration,cases}/       # cases/ = 10 casos PR completos (§14)
├── docs/                                  # Memoria, spec de implementación, plan de tareas
├── scripts/                               # Utilidades de desarrollo
└── .github/workflows/watchgate.yml       # Workflow de referencia (GitHub Action)
```

## Configuración

Pesos y umbrales de semáforo configurables por repositorio en `.watchgate.yml` (ver [`.watchgate.yml.example`](.watchgate.yml.example)):

```yaml
weights:    { static: 0.25, dependencies: 0.20, reputation: 0.15, semantic: 0.40 }
thresholds: { yellow: 31, red: 66 }
block_on_red: true
```

## Estado del desarrollo

En fase de diseño de arquitectura (memoria entregada). Implementación aún sin iniciar — arranca con el plan de trabajo de julio-agosto 2026 (ver memoria, secciones 5 y 6):

- [ ] Núcleo agnóstico de plataforma + interfaz común entre capas (A.0, A.0.0)
- [ ] Capa estática (Semgrep/YARA)
- [ ] Capa de dependencias (OSV, typosquatting)
- [ ] Capa de reputación
- [ ] Capa semántica (LLM + RAG local)
- [ ] Orquestador determinista + agregador de *scoring* (A.1, A.2)
- [ ] Adaptador de GitHub Action de referencia (A.0.1)
- [ ] Dashboard de postura de seguridad (2.1, A.4)
- [ ] Validación contra el conjunto de casos de prueba (≥10 casos)

## Resultado mínimo esperado

Núcleo de WatchGate como herramienta de línea de comandos, agnóstica de plataforma, con las cuatro capas de análisis operativas, dashboard de postura de seguridad completo (historial, *feedback* humano, SSO/OAuth con roles granulares), validado sobre al menos 10 casos representativos. Detalle en la memoria, sección 8.

## Referencias

- Wiz Research, *prt-scan*: [AI-Powered GitHub Actions Supply Chain Attack](https://www.wiz.io/blog/six-accounts-one-actor-inside-the-prt-scan-supply-chain-campaign)
- StepSecurity, [400+ AUR Packages Hijacked: the "Atomic Arch" Campaign](https://www.stepsecurity.io/blog/400-aur-packages-hijacked-atomic-arch-campaign)
- Datadog Security Labs, [BewAIre: detección de código malicioso en PRs con LLMs](https://www.datadoghq.com/blog/engineering/scaling-malicious-code-detection/)
- [GuardDog](https://github.com/DataDog/guarddog) · [Socket.dev](https://docs.socket.dev/docs/socket-for-github) · [Semgrep](https://semgrep.dev) · [OSV](https://osv.dev) · [GitHub Advisory Database](https://github.com/advisories)
