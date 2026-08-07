# Manual de Usuario e Integración de la CLI de WatchGate (`watchgate`)

## Metadatos

- **Autor / Responsable**: Equipo de Desarrollo e Infraestructura de WatchGate
- **Estado**: Documento Oficial de Referencia / Producción
- **Versión de la CLI**: 0.1.0
- **Última actualización**: 2026-08-07

---

# 1. Introducción

La Interfaz de Línea de Comandos (CLI) de WatchGate es el motor de ejecución principal del sistema de *scoring* de riesgo para Pull Requests. Diseñada bajo principios de portabilidad y arquitectura agnóstica, permite evaluar la seguridad de cambios en el código tanto de forma interactiva en la terminal del desarrollador como en pipelines de Integración Continua (CI/CD).

---

# 2. Instalación y Autocompletado

### 2.1 Instalación Local
Desde la raíz del proyecto WatchGate:

```bash
# Instalación editable en el entorno activo:
pip install -e .

# O usando el entorno virtual explícito:
.env/bin/pip install -e .
```

### 2.2 Configuración del Autocompletado de Shell (`argcomplete`)
WatchGate soporta autocompletado nativo para subcomandos, banderas y rutas en `bash` y `zsh`.

* **Bash:**
  ```bash
  eval "$(register-python-argcomplete watchgate)"
  ```
* **Zsh:**
  ```zsh
  autoload -U bashcompinit && bashcompinit
  eval "$(register-python-argcomplete watchgate)"
  ```

---

# 3. Ingesta de Diffs y Modos de Ejecución

WatchGate admite dos modos de lectura de parches de código:

### 3.1 Modo Repositorio Git Local
Compara dos commits, ramas o etiquetas en un repositorio local clonado en disco:

```bash
watchgate analyze --base main --head feature/nueva-funcionalidad --repo-path .
```

### 3.2 Modo Pipelines Unix (`stdin`)
Permite canalizar el parche directamente a través de la entrada estándar sin requerir un repositorio clonado:

```bash
git diff main..HEAD | watchgate analyze --diff-stdin --author-login octocat
```

> **Salvaguarda de Producción (Límite de Búfer):** La lectura por `stdin` tiene un límite máximo de **10 MB** (10,485,760 bytes) y requiere que la entrada provenga de un pipe o archivo no interactivo. Si no hay datos canalizados, la CLI aborta con código de salida `2`.

---

# 4. Formatos de Salida e Interoperabilidad CI/CD

La CLI soporta múltiples formatos de presentación adaptados a cada escenario:

### 4.1 Terminal Interactivo (`rich` TTY)
Cuando se ejecuta en un terminal interactivo (`sys.stdout.isatty()`) con el formato por defecto (`--format comment`), WatchGate renderiza el resultado con paneles de color, badges y tablas explicativas:

```bash
watchgate analyze --base HEAD~1 --head HEAD
```

### 4.2 Reporte Markdown (`--format comment`)
Genera la representación formateada en Markdown ideal para ser publicada como comentario de PR en GitHub/GitLab:

```bash
watchgate analyze --base HEAD~1 --head HEAD --format comment --output resultado.md
```

### 4.3 Formato JSON Estructurado (`--format json`)
Emite el contrato de datos completo (`AggregatedResult`) en JSON plano para ingesta programática en dashboards o SIEM:

```bash
watchgate analyze --base HEAD~1 --head HEAD --format json
```

### 4.4 Estándar SARIF v2.1.0 (`--format sarif`)
Exporta las vulnerabilidades y hallazgos en el estándar **SARIF 2.1.0** para su importación nativa en **GitHub Code Scanning**:

```bash
watchgate analyze --base HEAD~1 --head HEAD --format sarif --output results.sarif
```

> **Normalización de Rutas:** El generador de SARIF limpia las rutas absolutas de archivo convirtiéndolas en rutas relativas relativas a la raíz del proyecto para cumplir las especificaciones de GitHub Security.

### 4.5 Anotaciones de GitHub Actions (`--github-annotations`)
Emite comandos de flujo de trabajo (`::error::` / `::warning::`) para resaltar los hallazgos directamente en el diff del Pull Request en GitHub:

```bash
watchgate analyze --base HEAD~1 --head HEAD --github-annotations
```

> **Aislamiento de `stdout`:** Si `--github-annotations` se combina con `--format json` o `--format sarif`, las anotaciones se redirigen automáticamente a `sys.stderr` para no corromper la salida del archivo principal en `sys.stdout`.

---

# 5. Overrides Dinámicos de Parámetros

Puedes ajustar la ponderación de las capas de análisis o los umbrales de riesgo al vuelo sin editar el archivo `.watchgate.yml`:

### 5.1 Re-ponderación de Pesos (`--weight`)
```bash
watchgate analyze --base main --head dev \
  --weight static=0.40 \
  --weight semantic=0.40 \
  --weight dependencies=0.10 \
  --weight reputation=0.10
```

> **Re-normalización Automática:** Si la suma de los pesos difiere de `1.0`, WatchGate re-normalizará automáticamente cada peso dividiéndolo por la suma total y emitirá una advertencia (`WARNING`).

### 5.2 Ajuste de Umbrales (`--threshold`)
```bash
watchgate analyze --base main --head dev --threshold red=80 --threshold yellow=30
```

---

# 6. Control de Diagnóstico y Logs

* **`-q` / `--quiet`:** Silencia toda la salida por `stderr`. Únicamente se emite el informe final solicitado por `stdout`.
* **`-v` / `--verbose`:** Muestra registros informativos (`INFO`) con los tiempos de ejecución de las capas.
* **`--debug`:** Muestra información técnica detallada (`DEBUG`) incluyendo prompts LLM, tokens consumidos y consultas a la base de datos vectorial ChromaDB.

---

# 7. Códigos de Salida (*Exit Codes*)

| Código | Significado | Escenario de Disparo | Acción en CI/CD |
| :---: | :--- | :--- | :--- |
| **`0`** | **Éxito / Aprobado** | Análisis completado. Semáforo VERDE o AMARILLO (o ROJO si `block_on_red: false`). | Permite continuar el pipeline. |
| **`1`** | **Bloqueo de Política** | Veredicto global es **ROJO** y `block_on_red: true` está activo en la configuración. | Detiene el pipeline y bloquea el *merge*. |
| **`2`** | **Error de Usuario / Config** | Archivo `.watchgate.yml` corrupto, flags CLI erróneas, `stdin` sin datos o parche > 10 MB. | Falla la etapa por error de configuración. |
| **`3`** | **Error de Infraestructura** | Fallo crítico no recuperable de dependencias o de red en proveedores externos. | Alerta de fallo de infraestructura. |

---

# 8. Mantenimiento del Sistema RAG (`watchgate rag reindex`)

Reconstruye el índice vectorial de ChromaDB escaneando el corpus local de patrones de ataque:

```bash
watchgate rag reindex --index-path .watchgate/rag_index
```
