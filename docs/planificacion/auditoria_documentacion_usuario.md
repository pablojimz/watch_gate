# Auditoría de Documentación para Usuarios y Developer Experience (DX) de WatchGate

## Metadatos

- **Autor / Responsable**: Technical Writer Senior & Developer Advocate
- **Estado**: Finalizada / Evaluada para UX
- **Fecha de realización**: 2026-08-07
- **Objetivo**: Evaluar de forma integral la documentación orientada a usuarios finales, ingenieros DevOps y colaboradores externos para determinar si un usuario sin conocimientos previos del proyecto puede comprender qué hace, instalarlo, configurarlo, utilizarlo y solucionar problemas de forma autónoma.

---

# 1. Resumen Ejecutivo

Esta auditoría evalúa la **Experiencia de Desarrollo (DX)** y la **Calidad de la Documentación para Usuarios** de WatchGate. Tras analizar el recorrido completo de un usuario (*User Journey*) desde el descubrimiento inicial hasta la integración en pipelines de CI/CD y solución de problemas, se concluye que **WatchGate cuenta con una documentación para usuarios sumamente estructurada, clara y técnicamente rigurosa**.

Los documentos clave (`README.md`, `docs/manual_cli.md`, `.watchgate.yml.example`, `.env.example`) permiten a un nuevo usuario instalar la herramienta en 1 minuto, ejecutar su primer análisis local en 2 minutos y generar informes en formato Rich TTY, Markdown, JSON o SARIF v2.1.0.

* **Puntuación Global de Documentación de Usuario:** **9.0 / 10**
* **Evaluación General:** **Excelente**

---

# 2. Inventario de Documentación para Usuarios

| Documento / Recurso | Ubicación | Propósito | Público Objetivo | Nivel de Detalle | Estado |
| :--- | :--- | :--- | :--- | :---: | :---: |
| **`README.md`** | Raíz del repo | Presentación general, problema que resuelve, arquitectura simplificada y guía de inicio rápido. | Todos los perfiles | Alto | 🟢 Excelente |
| **`docs/manual_cli.md`** | `docs/manual_cli.md` | Manual de usuario de la CLI (`watchgate`): banderas, ingesta por `stdin`, SARIF, anotaciones CI/CD, exit codes. | Usuarios finales / DevOps | Exhaustivo | 🟢 Excelente |
| **`.watchgate.yml.example`** | Raíz del repo | Plantilla comentada para la configuración por repositorio (pesos, umbrales, bloqueos). | Usuarios finales / Admin | Práctico | 🟢 Excelente |
| **`.env.example`** | Raíz del repo | Plantilla de variables de entorno (API keys de LLMs, URLs de RAG, secreto del dashboard). | Administradores / Devs | Práctico | 🟢 Excelente |
| **`watchgate analyze --help`** | CLI binaria | Ayuda interactiva integrada en terminal con autocompletado `argcomplete`. | Usuarios de consola | Inmediato | 🟢 Excelente |
| **`docs/planificacion/mejoras_cli.md`** | `docs/planificacion/` | Especificación de reglas de producción (stdin, SARIF, GitHub Annotations en stderr). | Desarrolladores / Integradores | Técnico | 🟢 Excelente |
| **`docs/WatchGate_spec_implementacion_IA.md`** | `docs/` | Especificación interna de algoritmos, capas y modelos Pydantic. | Colaboradores / Arquitectos | Exhaustivo | 🟢 Excelente |

---

# 3. Evaluación del Recorrido del Usuario (*User Journey*)

### 3.1 🔍 Descubrimiento (Comprender el producto)
- **¿Qué es WatchGate?** Queda claro de inmediato en la primera línea de `README.md`: *"Sistema de scoring de riesgo para la revisión automatizada de pull requests en pipelines CI/CD"*.
- **¿Qué problema resuelve?** Se explica en la sección *"El problema"*: fatiga del revisor humano y ataques a la cadena de suministro por PRs maliciosas (ejemplos reales: Atomic Arch, XZ Utils).
- **¿Cuándo utilizarlo?** Para auditar automáticamente PRs en proyectos de código abierto o corporativos combinando análisis estático, dependencias, reputación del autor e IA semántica.
- **¿Cuándo NO utilizarlo?** Como sustituto único de pruebas unitarias o de integración funcional de la aplicación (WatchGate es un *security gate* de riesgo, no un runner de tests de software).

### 3.2 ⚙️ Instalación
- **Requisitos previos:** Python `>= 3.11` (declarado explícitamente en `pyproject.toml` y `README.md`).
- **Comando de instalación:**
  ```bash
  pip install -e .
  ```
- **Sistemas soportados:** Linux, macOS y Windows (entornos con Python 3.11+).
- **Verificación:** Ejecutando `watchgate analyze --help` o `.env/bin/watchgate --help`.

### 3.3 🎛️ Configuración
- **Mínima:** Funciona sin archivo `.watchgate.yml` usando valores por defecto seguros.
- **Por repositorio (`.watchgate.yml`):**
  ```yaml
  weights:    { static: 0.25, dependencies: 0.20, reputation: 0.15, semantic: 0.40 }
  thresholds: { yellow: 40, red: 70 }
  block_on_red: true
  ```
- **Variables de entorno (`.env`):**
  Soporta proveedores LLM mediante `WATCHGATE_LLM_PROVIDER` (`anthropic`, `gemini`, `local`).

### 3.4 🚀 Primer Uso ("Hello World")
Un usuario puede probar el sistema en 1 minuto contra su propio repositorio local:

```bash
# Analizar los cambios del último commit contra HEAD:
watchgate analyze --base HEAD~1 --head HEAD
```

### 3.5 🛠️ Uso Diario y Recetas de Integración
El manual `docs/manual_cli.md` proporciona recetas claras para los casos de uso más comunes:
1. **Ver salida interactiva TTY:** `watchgate analyze --base main --head mi-rama`
2. **Canalizar por pipe Unix:** `git diff main..HEAD | watchgate analyze --diff-stdin`
3. **Exportar a GitHub Code Scanning:** `watchgate analyze --base HEAD~1 --head HEAD --format sarif --output results.sarif`
4. **Resaltar en GitHub Actions:** `watchgate analyze --base HEAD~1 --head HEAD --github-annotations`
5. **Alterar pesos al vuelo:** `watchgate analyze --base main --head dev --weight static=0.35 --weight semantic=0.35`

---

# 4. Inconsistencias con el Código y Puntos de Fricción

Tras revisar los ejemplos y contrastarlos con el código fuente ejecutable, se han detectado los siguientes puntos de fricción menores:

1. **Comentario explicativo en `.env.example` (Línea 3):**
   - El comentario original decía *"Nada en el código carga .env automáticamente todavía (no hay CLI real aún...)"*.
   - **Inconsistencia:** La CLI ya es 100% funcional y la clase `WatchGateConfig` lee las variables de entorno `WATCHGATE_*` en tiempo de ejecución.
   - **Impacto:** Bajo (es solo una nota explicativa desactualizada en la cabecera del archivo de ejemplo).

2. **Falta de una sección dedicada de FAQ / Troubleshooting:**
   - Si un usuario no configura su API Key del LLM (`ANTHROPIC_API_KEY` o `GEMINI_API_KEY`), la capa semántica se marca automáticamente como `skipped=True` sin romper el análisis (mecanismo *degradación controlada*).
   - **Punto de fricción:** Un usuario novato puede preguntarse por qué la capa semántica muestra score 0 sin entender que le faltaba la API Key. Debe documentarse explícitamente en una sección de Troubleshooting.

3. **Inexistencia de un `docker-compose.yml` para el stack SaaS:**
   - La Engine API SaaS (`watchgate/api/`) y el Dashboard (`watchgate/dashboard/`) están documentados en `docs/planificacion/plan_implementacion_api.md`, pero no hay un archivo de inicio rápido Docker para usuarios no desarrolladores que quieran probar la interfaz web con PostgreSQL en 1 clic.

---

# 5. Evaluación de Calidad de la Documentación (Escala de Valoración)

| Criterio | Valoración | Justificación |
| :--- | :---: | :--- |
| **Claridad** | **Excelente** | Lenguaje directo, conciso y profesional. Explicaciones de parámetros con tipos y valores por defecto. |
| **Organización** | **Excelente** | Estructura jerárquica clara (`README.md` como puerta de entrada $\rightarrow$ `docs/manual_cli.md` como referencia). |
| **Completitud** | **Buena** | Cubre CLI, SARIF, GitHub Actions, RAG y LLMs. Falta guía de Troubleshooting/FAQ y guía de contribución. |
| **Exactitud** | **Excelente** | Todos los comandos y banderas CLI (`--diff-stdin`, `--format sarif`, `--github-annotations`, etc.) funcionan exactamente como se documenta. |
| **Ejemplos** | **Excelente** | Abundantes bloques de código ejecutable con sintaxis realista de Git y bash. |
| **Mantenibilidad** | **Excelente** | Documentos Markdown limpios en `docs/` con control de versiones. |

---

# 6. Plan de Mejoras Priorizado de Documentación de Usuario

### 🔴 Prioridad Alta (Acción Inmediata)
1. **Corregir comentario de cabecera en `.env.example`:**
   - Actualizar las líneas 1-5 de `.env.example` para aclarar que la CLI y `WatchGateConfig` leen automáticamente las variables de entorno con prefijo `WATCHGATE_`.
2. **Añadir sección de FAQ / Troubleshooting en `docs/manual_cli.md`:**
   - Explicar qué ocurre cuando no hay API Key de LLM (degradación controlada a `skipped=True`), cómo resolver errores de permisos en Git o cómo interpretar los códigos de salida `0, 1, 2, 3`.

### 🟡 Prioridad Media (Mejora de DX)
1. **Crear archivo `CONTRIBUTING.md`:**
   - Proporcionar una guía paso a paso para colaboradores que deseen enviar *Pull Requests* al repositorio (instrucciones para `pytest`, `ruff check`, `mypy`).
2. **Crear `docker-compose.yml` y documentar despliegue local de la Engine API:**
   - Añadir sección en `README.md` sobre cómo levantar la Engine API y el Dashboard web en contenedores.

### 🟢 Prioridad Baja (Calidad y Pulido)
1. **Añadir insignias (*Badges*) en `README.md`:**
   - Insignias de versión de Python (`>=3.11`), estado de tests (`pytest 288 passed`) y tipo de licencia.

---

# 7. Análisis sobre la Utilidad de esta Auditoría para la Auditoría Técnica Global

### ❓ ¿Es útil esta auditoría para actualizar la auditoría técnica y documental previa?

**Sí, es sumamente útil y complementaria por las siguientes razones:**

1. **Perspectiva Complementaria (Interna vs. Externa):**
   - La **Auditoría Técnica** (`docs/planificacion/auditoria_tecnica_y_documental.md`) evaluó la salud del sistema desde la perspectiva del **Arquitecto de Software** (calidad del código, patrones SOLID, cobertura de tests, desacoplamiento de capas y rendimiento).
   - La presente **Auditoría de Usuario** evalúa el sistema desde la perspectiva del **Developer Advocate y Usuario Final** (facilidad de adopción, experiencia en consola, solución de errores y onboarding).

2. **Identificación de Puntos Ciegos:**
   - La auditoría técnica le dio una puntuación de 9.0 a la documentación. Esta auditoría de usuario ha identificado detalles concretos que la auditoría técnica no vio a simple vista (como el texto desactualizado en la cabecera de `.env.example` o la ausencia de una sección de FAQ/Troubleshooting para degradación controlada de API Keys).

3. **Integración en un Único Marco de Calidad:**
   - Al incorporar estas recomendaciones en la auditoría técnica global, se logra una visión de 360 grados que garantiza que WatchGate no solo tenga un código excelente por dentro, sino también una experiencia de usuario impecable por fuera.
