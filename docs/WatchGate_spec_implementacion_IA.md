# WatchGate — Especificación de implementación (nivel "listo para IA")

Este documento es una especificación de construcción, no un resumen: cada apartado da interfaz exacta, algoritmo exacto, esquema exacto y criterio de aceptación exacto, de modo que un agente de codificación pueda implementarlo sin decisiones de diseño pendientes. Donde una decisión requiere juicio humano (p. ej. qué proveedor de LLM contratar), se marca explícitamente como `DECISIÓN HUMANA`.

Convención de esta spec: cada módulo tiene (1) Propósito, (2) Archivos a crear, (3) Interfaz/código, (4) Algoritmo paso a paso, (5) Casos límite, (6) Tests de aceptación.

---

## 0. Convenciones globales del repositorio

**Stack fijado** (para que el agente no tenga que decidir):
- Python 3.11+, gestor `uv` o `poetry` (usar `poetry`).
- Testing: `pytest` + `pytest-cov`. Cobertura mínima exigida: 80% en `core/`.
- Lint/format: `ruff` (lint + format en una sola herramienta).
- Tipado: `mypy --strict` sobre `core/`.
- CI local: `Makefile` con targets `install`, `lint`, `test`, `run-demo`.
- Logging: módulo estándar `logging`, formato JSON estructurado (`python-json-logger`), nunca `print`.
- Config: `pydantic-settings` para leer `.watchgate.yml` + variables de entorno, con validación de esquema en el arranque (fallar rápido si el YAML está mal formado).

**Estructura de repositorio (crear exactamente así):**

```
watchgate/
├── pyproject.toml
├── Makefile
├── .watchgate.yml.example
├── watchgate/                      # paquete Python instalable
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py                   # pydantic-settings, esquema de .watchgate.yml
│   ├── core/
│   │   ├── __init__.py
│   │   ├── diffparser.py
│   │   ├── models.py                # NormalizedDiff, FileChange, LayerResult
│   │   ├── layers/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── static_layer.py
│   │   │   ├── deps_layer.py
│   │   │   ├── reputation_layer.py
│   │   │   └── semantic_layer.py
│   │   ├── rag/
│   │   │   ├── __init__.py
│   │   │   ├── corpus/               # .md con casos documentados
│   │   │   ├── indexer.py
│   │   │   └── retriever.py
│   │   ├── orchestrator.py
│   │   ├── aggregator.py
│   │   └── cost_control.py
│   ├── adapters/
│   │   └── github_action/
│   │       ├── __init__.py
│   │       ├── main.py
│   │       └── github_client.py
│   └── dashboard/
│       ├── backend/
│       │   ├── main.py               # FastAPI app
│       │   ├── db.py
│       │   ├── auth.py
│       │   └── routers/
│       │       ├── scores.py
│       │       └── feedback.py
│       └── frontend/                 # SPA (React + Vite)
├── rules/
│   ├── semgrep/
│   └── yara/
├── datasets/
│   ├── few_shot/
│   └── typosquat_reference/          # top-N paquetes por ecosistema
├── tests/
│   ├── unit/
│   ├── integration/
│   └── cases/                        # fixtures de PRs completos
└── .github/workflows/watchgate.yml
```

**Definition of Done transversal** (aplica a cada módulo de esta spec): código con type hints, docstring en cada función pública, al menos un test unitario por rama lógica, y el módulo debe poder ejecutarse de forma aislada (`python -m watchgate.core.layers.static_layer` con un diff de ejemplo) sin necesitar el resto del sistema levantado.

---

## 1. `watchgate/core/models.py` — Contratos de datos (base de todo lo demás)

Implementar exactamente estas clases (usar `pydantic.BaseModel`, no `dataclass`, para tener validación y serialización JSON gratis):

```python
from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field

class FileStatus(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"

class FileChange(BaseModel):
    path: str
    old_path: str | None = None          # solo si status == RENAMED
    status: FileStatus
    diff_hunk: str                        # texto crudo del hunk unificado
    additions: int
    deletions: int
    is_binary: bool = False

class CommitAuthor(BaseModel):
    name: str
    email: str
    login: str | None = None              # username de plataforma, si el adaptador lo resuelve

class NormalizedDiff(BaseModel):
    base_sha: str
    head_sha: str
    repo_path: str
    files: list[FileChange]
    commit_messages: list[str]
    authors: list[CommitAuthor]

class RiskCategory(str, Enum):
    EXFILTRACION = "exfiltracion"
    BACKDOOR = "backdoor"
    OFUSCACION = "ofuscacion"
    ESCALADA_PRIVILEGIOS = "escalada_privilegios"
    NINGUNA = "ninguna"

class Confidence(str, Enum):
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"

class LayerResult(BaseModel):
    layer_name: str
    risk_score: int = Field(ge=0, le=100)
    justification: str
    category: RiskCategory | None = None   # solo la capa semántica lo rellena
    confidence: Confidence | None = None
    skipped: bool = False                  # true si la capa se desactivó o se omitió por presupuesto
    skip_reason: str | None = None
    tool_calls_made: int = 0               # solo semántica; para auditoría de A.3.1

class Semaforo(str, Enum):
    VERDE = "verde"
    AMARILLO = "amarillo"
    ROJO = "rojo"

class AggregatedResult(BaseModel):
    score: int = Field(ge=0, le=100)
    semaforo: Semaforo
    layer_results: dict[str, LayerResult]
    weights_used: dict[str, float]
    pr_id: str
    repo: str
    timestamp: str                          # ISO 8601
```

**Criterio de aceptación:** `AggregatedResult.model_dump_json()` debe producir exactamente el JSON que consumirá tanto el comentario de PR como el dashboard — es el contrato único entre todos los componentes. Ningún otro módulo define su propia versión de estas clases.

---

## 2. `watchgate/core/diffparser.py` — Extracción de primitivas git puras

**Propósito:** convertir `(repo_path, base_sha, head_sha)` en un `NormalizedDiff`, sin ninguna llamada de red.

**Dependencia:** `GitPython==3.1.*`.

**Interfaz:**
```python
def parse_diff(repo_path: str, base_sha: str, head_sha: str) -> NormalizedDiff: ...

def _extract_file_changes(repo: "git.Repo", base_sha: str, head_sha: str) -> list[FileChange]: ...

def _extract_commit_messages(repo: "git.Repo", base_sha: str, head_sha: str) -> list[str]: ...

def _extract_authors(repo: "git.Repo", base_sha: str, head_sha: str) -> list[CommitAuthor]: ...
```

**Algoritmo:**
1. Abrir el repo con `git.Repo(repo_path)`.
2. `diff_index = repo.commit(base_sha).diff(repo.commit(head_sha), create_patch=True)`.
3. Para cada `diff_item` en `diff_index`: mapear `diff_item.change_type` (`'A'`,`'M'`,`'D'`,`'R100'`...) a `FileStatus`; si `diff_item.diff` es bytes no decodificables como UTF-8, marcar `is_binary=True` y `diff_hunk=""`.
4. Contar `additions`/`deletions` parseando las líneas que empiezan por `+`/`-` en `diff_item.diff.decode("utf-8", errors="replace")`, excluyendo las líneas de cabecera (`+++`/`---`).
5. `commit_messages`: `list(repo.iter_commits(f"{base_sha}..{head_sha}"))`, tomar `.message.strip()` de cada uno.
6. `authors`: de los mismos commits, `.author.name` / `.author.email`; deduplicar por email conservando orden de aparición.

**Casos límite obligatorios a testear:**
- Diff vacío (`base_sha == head_sha`) → `files=[]`, no debe lanzar excepción.
- Archivo renombrado sin cambios de contenido → `status=RENAMED`, `additions=0, deletions=0`.
- Archivo binario (imagen) → `is_binary=True`, el resto de capas deben ignorar estos ficheros (filtrar en el orquestador o en cada capa, decidir en `base.py` y documentarlo).
- Historial con `merge commits` en medio → usar `--first-parent` implícitamente al iterar commits para no arrastrar commits de otras ramas ya fusionadas antes.

**Test de aceptación:** fixture con un repo git real generado en el test (`tempfile.mkdtemp()` + `git init` + dos commits), verificar que `parse_diff` devuelve exactamente los ficheros y autores esperados.

---

## 3. `watchgate/core/layers/base.py` — Interfaz común (A.0.0)

```python
from abc import ABC, abstractmethod
from watchgate.core.models import NormalizedDiff, LayerResult

class AnalysisLayer(ABC):
    name: str  # debe coincidir con la clave usada en .watchgate.yml -> weights

    @abstractmethod
    def analyze(self, diff: NormalizedDiff, metadata: dict) -> LayerResult:
        """Debe devolver siempre un LayerResult válido, nunca lanzar excepción
        no controlada. Cualquier error interno se captura y se traduce en
        LayerResult(skipped=True, skip_reason=str(e), risk_score=0)."""

LAYER_REGISTRY: dict[str, type[AnalysisLayer]] = {}

def register_layer(cls: type[AnalysisLayer]) -> type[AnalysisLayer]:
    LAYER_REGISTRY[cls.name] = cls
    return cls
```

Cada capa concreta se decora con `@register_layer` en su propio fichero; el orquestador nunca importa las clases concretas por nombre, solo instancia desde `LAYER_REGISTRY` según las claves con peso > 0 en la config. Esto es lo que garantiza "activación selectiva" y "extensión sin reescritura".

**Regla de arquitectura obligatoria (crear test `tests/unit/test_architecture.py`):** usar `import-linter` con un contrato `Layers` que prohíba que cualquier módulo bajo `watchgate/core/` importe algo de `watchgate/adapters/` o `watchgate/dashboard/`. Este test debe fallar el build si se viola.

**Wrapper de ejecución segura** (usar en el orquestador, no en cada capa): función `safe_analyze(layer, diff, metadata) -> LayerResult` que envuelve `layer.analyze(...)` en `try/except Exception as e` y devuelve `LayerResult(layer_name=layer.name, risk_score=0, justification="", skipped=True, skip_reason=repr(e))`.

---

## 4. `watchgate/core/layers/static_layer.py` — Capa estática (3a)

**Dependencias:** `semgrep` (CLI, invocado vía `subprocess`), `yara-python`.

**Reglas Semgrep a crear en `rules/semgrep/watchgate.yml`** (formato real de Semgrep, escribir las 5 reglas mínimas siguientes con `id`, `pattern`, `message`, `severity`, `languages`):

1. `eval-exec-dynamic`: detecta `eval(...)`, `exec(...)` (Python), `eval(...)`, `Function(...)` (JS) con argumento no literal. Severity: ERROR.
2. `shell-true-subprocess`: `subprocess.*(..., shell=True, ...)` con variable no constante. Severity: ERROR.
3. `curl-pipe-shell`: patrón textual `curl ... | sh` / `wget ... | bash` en scripts de shell o `Dockerfile`/`Makefile`. Severity: ERROR.
4. `privilege-escalation-write`: escritura a rutas `/etc/passwd`, `/etc/sudoers`, `~/.ssh/authorized_keys`. Severity: ERROR.
5. `network-call-in-build-script`: llamadas de red (`requests.get`, `fetch(`, `curl`, `Invoke-WebRequest`) dentro de ficheros de build (`setup.py`, `PKGBUILD`, `.github/workflows/*.yml`, `Makefile`). Severity: WARNING.

Además, usar registros públicos ya mantenidos: `semgrep --config p/security-audit --config p/secrets --config rules/semgrep/watchgate.yml`.

**Reglas YARA en `rules/yara/obfuscation.yar`:** al menos 2 reglas: `long_base64_blob` (cadena base64 de más de 200 caracteres contigua) y `hex_encoded_shellcode_pattern` (secuencias hex largas con alta entropía — calcular entropía de Shannon sobre substrings y marcar si > 4.5 bits/byte).

**Interfaz:**
```python
@register_layer
class StaticLayer(AnalysisLayer):
    name = "static"
    SEVERITY_SCORE = {"INFO": 10, "WARNING": 30, "ERROR": 60}  # + reglas propias "critical" a mano = 90

    def analyze(self, diff: NormalizedDiff, metadata: dict) -> LayerResult:
        ...
```

**Algoritmo:**
1. Escribir los hunks modificados de `diff` a ficheros temporales preservando extensión original (necesario para que Semgrep detecte el lenguaje).
2. Ejecutar `semgrep --config <rutas de arriba> --json <dir temporal>`, parsear `results[].extra.severity` y `results[].check_id`.
3. Ejecutar YARA sobre el mismo contenido (`yara.compile(filepaths=...).match(data=...)`).
4. `risk_score = max(SEVERITY_SCORE[s] for s in todas_las_severidades_disparadas)`, o `0` si no hay hallazgos. **No sumar** — tomar el máximo evita inflar el score por volumen de hallazgos menores (regla explícita del diseño).
5. `justification`: listar (máx. 3) los `check_id` disparados con severidad más alta, en una frase, p. ej. `"Detectado uso de eval() con entrada no literal (regla eval-exec-dynamic) y llamada de red en script de build."`
6. Limpiar ficheros temporales en un `finally`.

**Casos límite:** diff sin ficheros de código (solo `.md`/`.json` de datos) → `risk_score=0` sin ejecutar Semgrep (optimización, comprobar extensiones soportadas antes de invocar el subproceso). Ficheros binarios → excluir explícitamente de la entrada a Semgrep/YARA.

**Test de aceptación:** dos fixtures en `tests/cases/`: `benign_refactor/` (debe dar `risk_score < 20`) y `malicious_eval_base64/` (debe dar `risk_score >= 60`).

---

## 5. `watchgate/core/layers/deps_layer.py` — Capa de dependencias (3b)

**Dependencias:** `httpx` (cliente HTTP async/sync), `python-Levenshtein` (o `rapidfuzz`, más rápido) para typosquatting.

**Sub-parsers de manifiesto a implementar** (uno por ecosistema, todos con la misma firma):
```python
def parse_package_json(before: str, after: str) -> list[DependencyChange]: ...
def parse_requirements_txt(before: str, after: str) -> list[DependencyChange]: ...
def parse_pkgbuild(before: str, after: str) -> list[DependencyChange]: ...
```
```python
class DependencyChange(BaseModel):
    ecosystem: str            # "npm" | "pypi" | "aur"
    name: str
    old_version: str | None
    new_version: str | None
    is_new: bool
    install_script: str | None = None   # contenido de postinstall/preinstall/PKGBUILD si aplica
```

**Algoritmo principal:**
1. Detectar en `diff.files` si algún `path` coincide con `{"package.json", "requirements.txt", "Pipfile", "PKGBUILD", "Cargo.toml"}`.
2. Si no hay ninguno → devolver `LayerResult(risk_score=0, justification="No se han modificado manifiestos de dependencias.")` inmediatamente (no consultar red).
3. Para cada manifiesto tocado, usar el sub-parser correspondiente reconstruyendo el contenido antes/después a partir de `diff_hunk` (o, si el adaptador lo permite, leyendo el blob completo con `git show <sha>:<path>` — más robusto que parsear el hunk a mano).
4. Para cada `DependencyChange` con `is_new=True` o `new_version != old_version`:
   a. **Consulta OSV:** `POST https://api.osv.dev/v1/query` con body `{"package": {"name": name, "ecosystem": ecosystem}, "version": new_version}`. Cachear respuesta en SQLite (`~/.watchgate/cache.db`, tabla `osv_cache(name, ecosystem, version, response_json, fetched_at)`), TTL 24h.
   b. **Typosquatting:** cargar `datasets/typosquat_reference/<ecosystem>.txt` (lista de los top 5000 paquetes por descargas, actualizada manualmente cada cierto tiempo — `DECISIÓN HUMANA`: cadencia de actualización de este dataset). Calcular `rapidfuzz.distance.Levenshtein.distance(name, top_package)` para cada entrada; si `distance <= 2` y `name` no está en la propia lista (i.e. no es el paquete legítimo), marcar sospechoso.
   c. **Script de instalación:** si `install_script` no es `None`, re-ejecutar sobre él las mismas reglas Semgrep/YARA de la capa estática (reutilizar `StaticLayer._run_semgrep_on_text`, refactorizado como función compartida en `watchgate/core/layers/_shared.py` para no duplicar código entre capas).
5. Scoring: CVE de severidad `CRITICAL`/`HIGH` en OSV → 90; typosquatting probable → 75; script de instalación con hallazgos de red/ejecución → 80; ninguna señal → 10 (ligero, por el mero hecho de añadir una dependencia nueva sin verificar).
6. Tomar el máximo de todas las señales encontradas entre todas las dependencias tocadas (misma regla que la capa estática: máximo, no suma).

**Casos límite:** API de OSV caída/timeout → capturar excepción de `httpx`, marcar esa dependencia como "no verificable" en la justificación, **no** subir el score solo por el fallo de red (evitar falsos positivos por indisponibilidad del servicio), pero sí dejarlo dicho.

**Test de aceptación:** fixture con un `package.json` que añade una dependencia con nombre a distancia 1 de `"lodash"` (p. ej. `"1odash"`) → debe dar `risk_score >= 75` y `category` implícita de typosquatting en la justificación.

---

## 6. `watchgate/core/layers/reputation_layer.py` — Capa de reputación (3c)

**Entrada de metadata esperada** (contrato exacto que el adaptador debe rellenar, documentar en `models.py` como `ReputationMetadata`):
```python
class ReputationMetadata(BaseModel):
    author_login: str | None
    author_account_age_days: int | None
    author_prior_contributions_to_repo: int
    commit_email_matches_verified_email: bool
    commit_is_signed: bool
    signing_key_seen_before_for_login: bool | None   # None si no aplica (no firmado)
    repo_has_history_of_signed_commits: bool
```

**Tabla de puntuación (reglas explícitas, no ML):**

| Señal | Condición | Puntos |
|---|---|---|
| Cuenta muy nueva | `author_account_age_days < 30` | +30 |
| Cero contribuciones previas al repo | `author_prior_contributions_to_repo == 0` | +20 |
| Email no verificado | `not commit_email_matches_verified_email` | +25 |
| Repo firma habitualmente pero este commit no está firmado | `repo_has_history_of_signed_commits and not commit_is_signed` | +30 |
| Firmado pero con clave nunca vista para ese login | `commit_is_signed and signing_key_seen_before_for_login is False` | +40 |

**Algoritmo:** sumar los puntos de todas las señales que se cumplan, con tope en 100 (`min(100, total)`). Justificación: listar las señales concretas activadas, en lenguaje natural, citando los valores (p. ej. `"La cuenta autora tiene 4 días de antigüedad y no tiene contribuciones previas a este repositorio."`) — esto es clave porque es la capa que responde directamente al vector de Atomic Arch, y su output debe ser auditable por un humano sin ambigüedad.

**Nota de diseño a respetar:** esta capa **nunca** hace llamadas HTTP directamente; toda la metadata llega ya resuelta desde el adaptador (A.0.1). Si `metadata` no trae `ReputationMetadata` completo (p. ej. ejecución local sin adaptador), devolver `LayerResult(skipped=True, skip_reason="Sin metadatos de plataforma disponibles")`.

**Test de aceptación:** metadata simulando Atomic Arch (cuenta de 2 días, 0 contribuciones previas, email no verificado) → `risk_score >= 75`.

---

## 7. `watchgate/core/layers/semantic_layer.py` — Capa semántica (3d)

Este es el módulo más complejo; se subdivide en 4 piezas que deben implementarse como archivos separados dentro de `layers/_semantic/`: `prompting.py`, `tools.py`, `client.py`, `layer.py` (orquesta las tres anteriores).

### 7.1 `prompting.py` — Prompt de sistema exacto

```python
SYSTEM_PROMPT = """Eres un analista de seguridad de cadena de suministro de software.
Tu única tarea es evaluar si el cambio de código (diff) que se te presenta tiene
intención maliciosa, con independencia de quién parezca haberlo firmado: los
atacantes pueden falsificar nombre y correo de autor para simular continuidad
con el historial del proyecto. Evalúa el CONTENIDO del cambio, no la reputación
aparente del autor (esa señal la evalúa otro componente del sistema).

Contexto del proyecto:
- Tipo de proyecto: {project_type}
- Lenguaje(s) principal(es): {languages}
- Resumen de actividad reciente: {recent_activity_summary}

Casos de ataque conocidos recuperados como referencia (pueden no ser relevantes,
úsalos solo si el patrón realmente coincide):
{rag_context}

Debes responder ÚNICAMENTE con un objeto JSON que cumpla exactamente este esquema,
sin texto adicional antes o después:
{{
  "risk_score": <entero 0-100>,
  "category": <uno de: "exfiltracion", "backdoor", "ofuscacion", "escalada_privilegios", "ninguna">,
  "justification": "<una frase en español, concreta, citando la línea o construcción exacta del diff>",
  "confidence": <uno de: "alta", "media", "baja">
}}
"""

FEW_SHOT_EXAMPLES: list[dict] = [
    # cargar dinámicamente desde datasets/few_shot/*.json en tiempo de arranque,
    # cada fichero con forma {"diff_summary": str, "expected_output": {...}}
]
```

**Regla de construcción del prompt de usuario:** incluir el diff completo si su tamaño en tokens (calculado con el tokenizer del proveedor, ver `cost_control.py`) es menor que `max_diff_tokens` (config); si no, incluir solo los hunks ya marcados por la capa estática/dependencias como sospechosos, más un resumen textual del resto (`"... 340 líneas adicionales sin patrones detectados por análisis estático ..."`).

### 7.2 `tools.py` — Herramientas acotadas (A.3.1)

Definir los tres tools como funciones puras + su schema JSON para function-calling:

```python
def lookup_package_registry(name: str, ecosystem: str) -> dict: ...   # reutiliza el cliente OSV/npm/PyPI de deps_layer
def get_commit_history(author_login: str, repo: str) -> dict: ...      # vía adaptador, inyectado como callback
def fetch_referenced_file(path: str, ref: str, repo_path: str) -> str: ...  # git show local, sin red

TOOL_SCHEMAS = [
    {"name": "lookup_package_registry", "description": "...", "parameters": {...}},
    {"name": "get_commit_history", "description": "...", "parameters": {...}},
    {"name": "fetch_referenced_file", "description": "...", "parameters": {...}},
]
```

**Límite duro:** un contador `ToolCallBudget(max_calls=3)` pasado por referencia a lo largo de la conversación con el LLM; en cuanto se alcanza, la siguiente respuesta del modelo se fuerza a "responde ya sin más herramientas" añadiendo un mensaje de sistema adicional (`"Ya has usado el máximo de herramientas permitidas. Responde ahora con el JSON final."`).

### 7.3 `client.py` — Cliente del proveedor LLM

**`DECISIÓN HUMANA`:** qué proveedor usar (Anthropic API, OpenAI, modelo local vía Ollama). Implementar detrás de una interfaz para que sea sustituible sin tocar el resto (cumple A.0.0 aplicado también aquí):

```python
class LLMClient(ABC):
    @abstractmethod
    def complete_structured(self, system_prompt: str, user_prompt: str,
                             tools: list[dict], max_tool_calls: int) -> SemanticOutput: ...

class AnthropicClient(LLMClient): ...   # implementación concreta inicial
```

`SemanticOutput` es un `pydantic.BaseModel` igual al esquema de 7.1; si el proveedor no soporta salida estructurada nativa, parsear el texto de respuesta con `json.loads` dentro de un `try/except`, y si falla, reintentar una vez añadiendo `"Tu respuesta anterior no era JSON válido. Responde solo con el JSON."`; si falla una segunda vez, devolver `LayerResult(skipped=True, skip_reason="LLM no devolvió JSON válido tras 2 intentos")`.

### 7.4 RAG (`watchgate/core/rag/`) — A.3.2

**`indexer.py`:**
1. Leer todos los `.md` de `core/rag/corpus/` (uno por caso: `xz_utils.md`, `prt_scan.md`, `atomic_arch.md`, más entradas de MITRE ATT&CK/CAPEC relevantes, resumidas a mano — `DECISIÓN HUMANA`: qué técnicas de ATT&CK incluir, sugerido: T1195 Supply Chain Compromise, T1027 Obfuscated Files, T1548 Abuse Elevation Control).
2. Trocear cada documento en fragmentos de ~200-300 tokens (`langchain_text_splitters.RecursiveCharacterTextSplitter` o implementación propia simple).
3. Generar embeddings con `sentence-transformers` (`all-MiniLM-L6-v2`, corre en CPU, no requiere API externa — respeta el requisito de "puede ejecutarse íntegramente sin salir de la red del cliente").
4. Persistir en `chromadb` local (`PersistentClient(path=".watchgate/rag_index")`), colección `attack_patterns`, metadata `{source, case_name}` por fragmento.
5. Este indexado se ejecuta una vez (`watchgate rag reindex`), no en cada análisis de PR.

**`retriever.py`:**
```python
def retrieve_relevant_context(diff_summary: str, k: int = 3) -> list[RetrievedFragment]: ...
```
Genera embedding del resumen del diff (concatenación de nombres de fichero + primeras líneas de cada hunk sospechoso), consulta la colección con `collection.query(query_embeddings=[...], n_results=k)`, devuelve texto + `case_name` de cada fragmento para inyectar en `rag_context` del prompt.

### 7.5 `layer.py` — Orquesta todo lo anterior

```python
@register_layer
class SemanticLayer(AnalysisLayer):
    name = "semantic"

    def analyze(self, diff: NormalizedDiff, metadata: dict) -> LayerResult:
        # 1. cost_control.should_skip(diff) -> si True, LayerResult(skipped=True, ...)
        # 2. cost_control.check_cache(diff_hash) -> si hit, devolver cacheado
        # 3. rag_context = retriever.retrieve_relevant_context(...)
        # 4. prompt = prompting.build_prompt(diff, metadata, rag_context)
        # 5. output = client.complete_structured(prompt, tools=TOOL_SCHEMAS, max_tool_calls=3)
        # 6. cost_control.store_cache(diff_hash, output)
        # 7. return LayerResult(layer_name="semantic", risk_score=output.risk_score, ...)
        ...
```

**Test de aceptación:** con un `LLMClient` *fake* inyectado por dependencia (patrón de inyección de dependencias explícito, no import directo, para poder testear sin llamar a ninguna API real), verificar que el flujo completo (RAG → prompt → parseo → cache) funciona con una respuesta simulada.

---

## 8. `watchgate/core/cost_control.py` — Control de coste (A.3.3)

```python
class CostController:
    def __init__(self, db_path: str, max_diff_tokens: int, monthly_budget_tokens: int): ...

    def estimate_tokens(self, text: str) -> int: ...          # usar tokenizer del proveedor (p.ej. tiktoken si aplica, o el contador propio del SDK)
    def should_truncate(self, diff: NormalizedDiff) -> bool: ...
    def truncate_diff(self, diff: NormalizedDiff, static_findings: list) -> NormalizedDiff: ...
    def get_cached(self, diff_hash: str) -> SemanticOutput | None: ...
    def store_cached(self, diff_hash: str, output: SemanticOutput) -> None: ...
    def record_usage(self, repo: str, tokens_used: int) -> None: ...
    def budget_remaining(self, repo: str) -> int: ...
```

**Esquema SQLite** (`~/.watchgate/cost.db`):
```sql
CREATE TABLE semantic_cache (diff_hash TEXT PRIMARY KEY, output_json TEXT, created_at DATETIME);
CREATE TABLE token_usage (repo TEXT, month TEXT, tokens_used INTEGER, PRIMARY KEY (repo, month));
```

**Algoritmo de truncado (`truncate_diff`):** ordenar los `FileChange` por si tienen hallazgos previos de `static_layer`/`deps_layer` (pasados como argumento `static_findings`), incluir esos completos primero, y para el resto incluir solo los primeros N caracteres de cada hunk con un marcador `"[...truncado, N líneas adicionales sin hallazgos previos...]"` hasta alcanzar `max_diff_tokens`.

**`diff_hash`:** `hashlib.sha256(json.dumps(diff.model_dump(), sort_keys=True).encode()).hexdigest()` — determinista, mismo diff exacto (tras un rebase sin cambios) produce el mismo hash.

**Degradación controlada:** si `budget_remaining(repo) <= 0`, `SemanticLayer.analyze` debe devolver `LayerResult(skipped=True, skip_reason="Presupuesto de tokens agotado para este repositorio este mes", risk_score=0)` **antes** de llamar al LLM.

**Test de aceptación:** simular presupuesto agotado y verificar que no se realiza ninguna llamada de red (mockear el cliente HTTP y aserír `call_count == 0`).

---

## 9. `watchgate/core/orchestrator.py` — A.1

```python
def run_analysis(diff: NormalizedDiff, metadata: dict, config: WatchGateConfig) -> AggregatedResult:
    active_layers = [
        LAYER_REGISTRY[name]()
        for name, weight in config.weights.items()
        if weight > 0 and name in LAYER_REGISTRY
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(active_layers) or 1) as pool:
        futures = {pool.submit(safe_analyze, layer, diff, metadata): layer.name for layer in active_layers}
        results = {futures[f]: f.result() for f in concurrent.futures.as_completed(futures)}
    return aggregate(results, config.weights, diff, pr_id=metadata.get("pr_id"), repo=metadata.get("repo"))
```

**Regla explícita:** este archivo no debe contener ningún `if` que decida *qué* capa ejecutar más allá del filtro por peso > 0 leído de config. Cualquier lógica condicional adicional (p. ej. los cortocircuitos de A.3.4) vive en un módulo aparte (`shortcircuit.py`) que se invoca *antes* de `run_analysis` y puede evitar llamarla del todo — nunca dentro de esta función.

**Test de aceptación:** test con 4 capas *fake* (una que tarda 2s simulando latencia de red) y verificar que el tiempo total de `run_analysis` es ~2s (paralelo) y no ~8s (secuencial).

---

## 10. `watchgate/core/aggregator.py` — A.2

```python
def aggregate(results: dict[str, LayerResult], weights: dict[str, float],
              diff: NormalizedDiff, pr_id: str, repo: str) -> AggregatedResult:
    active = {k: v for k, v in results.items() if not v.skipped and weights.get(k, 0) > 0}
    total_weight = sum(weights[k] for k in active) or 1e-9
    score = round(sum(weights[k] * active[k].risk_score for k in active) / total_weight)
    semaforo = _semaforo(score, thresholds)
    return AggregatedResult(score=score, semaforo=semaforo, layer_results=results,
                             weights_used=weights, pr_id=pr_id, repo=repo,
                             timestamp=datetime.utcnow().isoformat())

def _semaforo(score: int, thresholds: dict) -> Semaforo:
    if score >= thresholds["red"]: return Semaforo.ROJO
    if score >= thresholds["yellow"]: return Semaforo.AMARILLO
    return Semaforo.VERDE
```

**Plantilla de comentario** (`watchgate/core/comment_template.py`, usar `jinja2`), reproduciendo exactamente el formato de la memoria:

```jinja2
[{{ semaforo_emoji }}] WatchGate: Riesgo {{ semaforo_texto }} ({{ score }}/100)

{% for name, result in layer_results.items() %}
{{ name | capitalize }}{{ " " * padding }}{{ result.risk_score }}/100  (peso {{ weights_used[name] }}){% if result.skipped %} — omitida: {{ result.skip_reason }}{% endif %}
{% endfor %}

Justificación (capa semántica):
"{{ layer_results['semantic'].justification }}"

-> {{ recomendacion_por_semaforo }}
```

**Test de aceptación:** dado el ejemplo exacto de la memoria (estática 20, deps 10, reputación 40, semántica 85, pesos 0.25/0.20/0.15/0.40) el resultado debe ser `score == 47` y `semaforo == AMARILLO`. Este es un test de regresión literal contra el documento original — no debe fallar nunca.

---

## 11. `watchgate/core/shortcircuit.py` — A.3.4 (opcional, objetivo ampliado)

```python
FORCING_PATTERNS = [r"PKGBUILD$", r"^\.github/workflows/", r"Makefile$", r"Dockerfile$"]

def evaluate_shortcircuit(partial_results: dict[str, LayerResult], weights: dict,
                           diff: NormalizedDiff, thresholds: dict) -> Semaforo | None:
    """Devuelve un Semaforo si se puede cortocircuitar sin llamar a la capa semántica,
    o None si hay que ejecutarla igualmente."""
    partial_score = _weighted_partial(partial_results, weights)  # solo static+deps+reputation
    if partial_score >= thresholds["red"]:
        return Semaforo.ROJO   # alto riesgo: no reabre falsos negativos porque el score combinado solo puede subir o igualar
    forces_semantic = _matches_forcing_pattern(diff, FORCING_PATTERNS) or _has_new_network_calls(diff) or _has_new_dependencies(diff)
    if partial_score < thresholds["yellow"] * 0.5 and not forces_semantic:
        if random.random() < 1 / 20:   # muestreo de auditoría configurable
            return None  # forzar semántica igualmente, registrar en audit_sampling table
        return Semaforo.VERDE
    return None
```

**Nota de invocación:** este módulo se llama *antes* de instanciar `SemanticLayer` en el orquestador, solo si `config.shortcircuit_enabled: true`. Si devuelve un `Semaforo`, el orquestador debe registrar igualmente un `LayerResult(skipped=True, skip_reason="Cortocircuito de extremo aplicado")` para la capa semántica, para que el dashboard sepa que no se ejecutó.

---

## 12. `watchgate/adapters/github_action/` — A.0.1

**`github_client.py`** — wrapper fino sobre la API REST de GitHub (`httpx` + `GITHUB_TOKEN`):
```python
class GitHubClient:
    def get_pr_diff_shas(self, pr_event: dict) -> tuple[str, str]: ...
    def get_reputation_metadata(self, owner: str, repo: str, author_login: str) -> ReputationMetadata: ...
    def post_comment(self, owner: str, repo: str, pr_number: int, body: str) -> None: ...
    def post_check_run(self, owner: str, repo: str, sha: str, conclusion: str, summary: str) -> None: ...
```

**`main.py`** (entrypoint de la Action):
1. Leer `GITHUB_EVENT_PATH` (variable estándar de GitHub Actions) → parsear JSON del evento `pull_request`.
2. Extraer `base_sha`, `head_sha`, `owner`, `repo`, `pr_number`, `author_login`.
3. `diff = parse_diff(repo_path=".", base_sha, head_sha)` (repo ya clonado por `actions/checkout@v4` con `fetch-depth: 0`).
4. `reputation_metadata = github_client.get_reputation_metadata(...)`.
5. `result = run_analysis(diff, metadata={"reputation": reputation_metadata, "pr_id": pr_number, "repo": f"{owner}/{repo}"}, config=load_config(".watchgate.yml"))`.
6. `github_client.post_comment(...)` con el comentario renderizado por `comment_template`.
7. `github_client.post_check_run(..., conclusion="failure" if result.semaforo == ROJO and config.block_on_red else "neutral")`.
8. Persistir `result` en la base de datos del dashboard (llamada HTTP al backend, o escritura directa si backend y Action comparten infraestructura — `DECISIÓN HUMANA` según el hosting elegido).
9. `sys.exit(1)` si `conclusion == "failure"` para que el *check* de CI se marque como fallido.

**`.github/workflows/watchgate.yml`** (contenido exacto, copiar literal de la memoria, añadiendo instalación del paquete):
```yaml
name: WatchGate
on:
  pull_request:
    types: [opened, synchronize]
jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install watchgate
      - run: watchgate analyze --base ${{ github.event.pull_request.base.sha }} --head ${{ github.sha }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          WATCHGATE_LLM_API_KEY: ${{ secrets.WATCHGATE_LLM_API_KEY }}
```

**Test de seguridad obligatorio:** un test que ejecute la Action en modo simulado (`act` o un test de integración con variables fake) y haga `grep` sobre toda la salida de logs buscando el valor literal de `WATCHGATE_LLM_API_KEY` — el test falla si aparece.

---

## 13. `watchgate/dashboard/backend/` — A.4

**`db.py`** — esquema exacto (SQLite para el prototipo; documentar migración a Postgres como nota, no implementarla ahora):
```sql
CREATE TABLE pr_scores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repo TEXT NOT NULL,
  pr_number INTEGER NOT NULL,
  timestamp DATETIME NOT NULL,
  score INTEGER NOT NULL,
  semaforo TEXT NOT NULL,
  static_score INTEGER, static_skipped BOOLEAN,
  deps_score INTEGER, deps_skipped BOOLEAN,
  reputation_score INTEGER, reputation_skipped BOOLEAN,
  semantic_score INTEGER, semantic_skipped BOOLEAN, semantic_justification TEXT,
  human_feedback TEXT CHECK(human_feedback IN ('correcto','falso_positivo') OR human_feedback IS NULL)
);
CREATE INDEX idx_repo_timestamp ON pr_scores(repo, timestamp);

CREATE TABLE repo_roles (
  user_login TEXT NOT NULL, repo TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin_organizacion','mantenedor','revisor')),
  PRIMARY KEY (user_login, repo)
);
```

**`auth.py`** — flujo OAuth de GitHub:
1. `GET /auth/github/login` → redirige a `https://github.com/login/oauth/authorize?client_id=...&scope=read:org,repo`.
2. `GET /auth/github/callback?code=...` → intercambia `code` por `access_token` (`POST https://github.com/login/oauth/access_token`), obtiene `login` del usuario (`GET /user`), emite una cookie de sesión firmada (JWT con `itsdangerous` o `python-jose`).
3. Middleware `get_current_user(request) -> User` que decodifica la cookie en cada request.
4. `resolve_role(user_login, repo)`: si no existe fila en `repo_roles`, consultar `GET /repos/{owner}/{repo}/collaborators/{user_login}/permission` y mapear `"admin"|"write"` → `mantenedor`, `"read"` → `revisor`; persistir el resultado en `repo_roles` como default (ajustable luego manualmente por un admin).
5. Segunda vía OIDC genérica: mismo patrón con `authlib` apuntando a la configuración de Auth0/Keycloak (`DECISIÓN HUMANA`: cuál de los dos proveedores OIDC contratar) — implementar como segundo router `auth_oidc.py` que produzca la misma cookie de sesión, de forma que el resto del backend no distinga cómo se autenticó el usuario.

**`routers/scores.py`:**
```python
@router.get("/repos/{repo}/scores")
def list_scores(repo: str, user: User = Depends(get_current_user)) -> list[AggregatedResult]:
    require_role(user, repo, min_role="revisor")
    ...

@router.get("/repos")
def list_visible_repos(user: User = Depends(get_current_user)) -> list[str]:
    ...  # admin_organizacion ve todos, el resto solo los suyos en repo_roles
```

**`routers/feedback.py`:**
```python
@router.post("/scores/{score_id}/feedback")
def submit_feedback(score_id: int, feedback: FeedbackIn, user: User = Depends(get_current_user)) -> None:
    require_role(user, repo_of(score_id), min_role="mantenedor")
    ...  # UPDATE pr_scores SET human_feedback = ...
```

**Tabla de permisos a implementar en `require_role` (exactamente la de la memoria):**

| Acción | admin_organizacion | mantenedor | revisor |
|---|---|---|---|
| Ver histórico/desglose | ✓ | ✓ | ✓ |
| Ajustar pesos/umbrales | ✓ | ✓ (solo sus repos) | ✗ |
| Resolver feedback humano | ✓ | ✓ | ✗ |
| Gestionar accesos | ✓ | ✗ | ✗ |

**Test de aceptación:** test de integración con `TestClient` de FastAPI simulando los 3 roles contra los 4 endpoints, verificando 403 exactamente donde la tabla dice ✗.

### Frontend (`dashboard/frontend/`)

**`DECISIÓN HUMANA`:** framework — se recomienda React + Vite + TypeScript por ser el stack más simple de mantener para un equipo de 3 con tiempo limitado.

Páginas mínimas:
1. `/login` — botón "Entrar con GitHub".
2. `/repos` — lista de repos visibles según rol.
3. `/repos/:repo` — gráfico de línea (score en el tiempo, librería `recharts`) + tabla de PRs recientes con desglose por capa al expandir fila.
4. `/repos/:repo/feedback` — tabla de PRs con score y botones "Correcto"/"Falso positivo" (solo visible si rol ≥ mantenedor).
5. `/admin` — gestión de `repo_roles` (solo `admin_organizacion`).

---

## 14. Suite de pruebas de aceptación end-to-end (sección 8 de la memoria)

**Estructura de cada caso en `tests/cases/<nombre>/`:**
```
tests/cases/atomic_arch_simulado/
├── repo/              # repo git real con 2 commits (base y head)
├── expected.json      # {"semaforo": "rojo", "min_score": 66}
└── metadata.json       # ReputationMetadata simulado para este caso
```

**Casos mínimos obligatorios (10, tal como exige la sección 8):**
1. `benign_refactor` → verde
2. `benign_new_feature_with_new_dep` → verde/amarillo
3. `malicious_eval_base64` → rojo
4. `malicious_curl_pipe_bash_in_dockerfile` → rojo
5. `typosquat_dependency` → rojo
6. `cve_known_vulnerable_dependency` → amarillo/rojo
7. `atomic_arch_simulado` (identidad falsificada, PKGBUILD modificado) → rojo
8. `xz_utils_simulado` (backdoor sutil en script de build, introducido gradualmente) → amarillo/rojo
9. `prt_scan_simulado` (PR generado por IA con payload adaptado al lenguaje del proyecto) → rojo
10. `false_positive_candidate` (uso legítimo de `eval()` en un intérprete conocido, comentado y testeado) → amarillo, para medir calibración, no necesariamente verde

**Test runner (`tests/integration/test_cases.py`):**
```python
@pytest.mark.parametrize("case_dir", discover_cases("tests/cases"))
def test_case(case_dir):
    expected = json.loads((case_dir / "expected.json").read_text())
    result = run_full_pipeline(case_dir)
    assert result.semaforo.value == expected["semaforo"]
    assert result.score >= expected.get("min_score", 0)
```

**Informe de validación (entregable final):** generar automáticamente `docs/validation_report.md` a partir de los resultados de este test runner (tabla caso/esperado/obtenido/score), no escribirlo a mano — así se regenera en cada ejecución de CI y nunca queda desactualizado respecto al código real.

---

## 15. Orden de implementación recomendado para un agente autónomo

Si una IA va a implementar esto de principio a fin sin supervisión constante, este es el orden que minimiza retrabajo (cada paso es testeable de forma aislada antes de pasar al siguiente):

1. §1 `models.py` (sin esto nada más compila).
2. §2 `diffparser.py` + sus tests (núcleo de A.0, sin red).
3. §3 `base.py` + registro de capas + test de arquitectura (import-linter).
4. §4 `static_layer.py` (la capa más autocontenida, sin dependencias externas de red).
5. §10 `aggregator.py` (se puede testear con `LayerResult` construidos a mano, sin esperar a tener las 4 capas reales).
6. §9 `orchestrator.py` (con capas *fake* inyectadas).
7. §5 `deps_layer.py`.
8. §6 `reputation_layer.py`.
9. §8 `cost_control.py` (antes que la capa semántica, porque esta depende de él).
10. §7 `semantic_layer.py` completa (prompting → tools → RAG → client), con `LLMClient` *fake* primero, proveedor real al final.
11. §12 adaptador GitHub Action.
12. §13 backend del dashboard.
13. Frontend del dashboard.
14. §11 cortocircuitos (opcional).
15. §14 suite de 10 casos + informe de validación automático.

Cada uno de estos 15 pasos debe terminar con `make test` en verde antes de empezar el siguiente — no acumular deuda de tests pendientes entre módulos.
