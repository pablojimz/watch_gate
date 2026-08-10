# Desplegar WatchGate en una máquina GPU para probar modelos locales

Este documento cubre cómo levantar WatchGate en una máquina Linux con GPU
(pensado para algo del tamaño de una A100 de 40GB, pero cualquier GPU con
suficiente VRAM sirve) para poder probar la capa semántica contra modelos
servidos localmente -- en vez de (o además de) los proveedores cloud
(Anthropic/Gemini) que usa el proyecto por defecto.

No asume ningún proveedor de nube concreto (GCP, AWS, on-prem...) -- todo
lo de aquí es agnóstico de dónde viva la máquina, solo asume Linux +
NVIDIA + acceso SSH. Si en algún momento hay que adaptar algo específico
del proveedor real (por ejemplo, la imagen exacta de arranque), es un
añadido a este documento, no una reescritura.

## Por qué esto es sencillo: el proyecto ya soporta modelos locales

`watchgate/core/layers/_semantic/llm_factory.py` ya selecciona el
proveedor LLM por variable de entorno (`WATCHGATE_LLM_PROVIDER`:
`anthropic` | `gemini` | `local`) sin ningún cambio de código. El modo
`local` habla el protocolo de chat completions de OpenAI contra cualquier
servidor que lo implemente (Ollama, llama.cpp server, LM Studio, vLLM...)
-- basta con apuntar `WATCHGATE_LLM_BASE_URL` al servidor correspondiente.
Todo lo que hace falta para "probar distintos modelos y configuraciones"
es: levantar un servidor de inferencia en la máquina GPU, y cambiar dos
variables de entorno para apuntar WatchGate a él.

Se recomienda **vLLM** como servidor de inferencia (no Ollama) porque:
- Aprovecha de verdad una GPU de centro de datos (batching continuo,
  paginación de KV-cache) -- Ollama está pensado para uso local en
  portátil/estación de trabajo, no para exprimir una A100.
- Su servidor OpenAI-compatible soporta *tool calling* de verdad
  (`--enable-auto-tool-choice`), que es exactamente lo que necesita la
  capa semántica (`fetch_referenced_file`, `lookup_package_registry`,
  `check_file_reputation`, `get_commit_history` -- ver
  `_semantic/tools.py`). Sin tool calling que funcione, la capa semántica
  sigue respondiendo (el esquema estructurado no lo necesita), pero pierde
  toda la capacidad de verificar contenido truncado o consultar señales
  externas -- una degradación silenciosa que conviene evitar desde el
  principio.

## 1. Provisionar la máquina

```bash
# En la máquina GPU (Ubuntu 22.04/24.04 asumido; ajustar si es otra distro):
git clone <url-del-repo> watch_gate   # o rsync/scp desde el checkout local
cd watch_gate
./scripts/provision_gpu_vm.sh
```

`scripts/provision_gpu_vm.sh` (nuevo, ver el propio fichero) hace, en este
orden:

1. Comprueba `nvidia-smi` -- si no hay driver NVIDIA instalado, avisa y
   para ahí (instalar el driver correcto depende de la imagen/proveedor
   concreto, fuera de alcance de un script genérico).
2. Comprueba/instala Python ≥3.11 (`requires-python` de `pyproject.toml`)
   y Poetry.
3. `poetry install` -- las dependencias normales de WatchGate (sin vLLM,
   ver el porqué del venv separado más abajo).
4. Crea un **venv Python separado** (`.venv-vllm/`, fuera del árbol que
   gestiona Poetry) e instala `vllm` ahí.
5. Imprime los siguientes pasos (sección 2 de este documento).

### Por qué vLLM vive en un venv aparte, no como dependencia de Poetry

`vllm` fija versiones muy concretas de `torch`/CUDA que casi seguro no
coinciden con la versión de `torch` que ya trae `sentence-transformers`
(dependencia real del proyecto, para los embeddings del RAG local -- ver
`core/rag/indexer.py`). Meter `vllm` en el mismo entorno que gestiona
`poetry.lock` arriesga con romper esa resolución para todo el mundo,
incluida la gente que solo quiere correr tests en su portátil sin GPU.
vLLM es una herramienta operativa (un servidor que se lanza aparte),
no una dependencia de la librería -- vive en su propio venv, con su propio
`pip install vllm`, sin tocar `pyproject.toml`/`poetry.lock`.

## 2. Servir un modelo

```bash
./scripts/serve_local_model.sh <preset|model-id-de-huggingface>
```

`scripts/serve_local_model.sh` (nuevo) activa `.venv-vllm/` y lanza
`vllm serve` con los flags correctos para cada preset, incluido el
`--tool-call-parser` correcto para esa familia de modelo (crítico: sin el
parser adecuado, el servidor acepta la petición pero el tool calling no
funciona de verdad, y falla en silencio de formas raras). Presets
incluidos, pensados para caber cómodos en una GPU de 40GB con margen para
KV-cache:

| Preset | Modelo | VRAM aprox. (pesos) | Cuándo usarlo |
|---|---|---:|---|
| `llama3.1-8b` | `meta-llama/Llama-3.1-8B-Instruct` | ~16 GB (FP16) | Iteración rápida y barata; línea base para comparar contra los proveedores cloud. |
| `qwen2.5-14b` | `Qwen/Qwen2.5-14B-Instruct` | ~28 GB (FP16) | Más capacidad de razonamiento que 8B, sigue holgado en 40GB. |
| `qwen2.5-32b-awq` | `Qwen/Qwen2.5-32B-Instruct-AWQ` | ~19 GB (AWQ 4-bit) | El modelo más capaz que cabe con margen real para batching/contexto largo. |

Los tres son solo un punto de partida razonable, no una lista cerrada --
`serve_local_model.sh` acepta cualquier `model-id` de HuggingFace
directamente; para uno no listado en los presets, hay que añadir a mano el
`--tool-call-parser` adecuado (consultar `vllm serve --help` en la propia
máquina: los nombres de parser han cambiado entre versiones de vLLM, así
que la lista de esta tabla puede quedar desactualizada -- verificar ahí,
no fiarse solo de este documento).

El servidor queda escuchando en `http://localhost:8000/v1`
(OpenAI-compatible) por defecto.

## 3. Apuntar WatchGate al modelo servido

```bash
cp .env.example .env
```

Y en `.env`:

```bash
WATCHGATE_LLM_PROVIDER=local
WATCHGATE_LLM_BASE_URL=http://localhost:8000/v1
WATCHGATE_LLM_MODEL=meta-llama/Llama-3.1-8B-Instruct   # el mismo model-id que serviste en el paso 2
```

`WATCHGATE_LLM_MODEL` debe coincidir exactamente con el `model-id` que
`vllm serve` tiene cargado -- vLLM lo usa para verificar que la petición
va dirigida al modelo que de verdad tiene en memoria.

## 4. Verificar que funciona de verdad, no solo "responde"

```bash
set -a && source .env && set +a
poetry run python scripts/smoke_test_linea2.py --repo . --label "primera-prueba-$(hostname)"
```

Esto ejecuta `ReputationLayer` + `SemanticLayer` reales contra un diff real
del propio repo, sin mocks. Si el modelo servido no soporta tool calling
correctamente, es aquí donde se ve -- el smoke test no falla en silencio,
y queda registrado en `.watchgate/semantic_layer_log.jsonl` (gitignored)
para poder comparar entre ejecuciones sin repetir la llamada.

Para una comparación real contra la suite de 193 casos (mismo mecanismo
que `docs/validation_report.md`, pero apuntado al modelo local en vez de
Gemini):

```bash
poetry run python -m tests.integration.generate_validation_report
```

Esto sobrescribe `docs/validation_report.md`/`_raw.json` -- si se quiere
comparar varios modelos/configuraciones lado a lado sin perder el
resultado anterior, copiar esos dos ficheros a un nombre aparte
(`docs/validation_report_<preset>.md`) entre una ejecución y la siguiente
antes de cambiar de modelo y volver a lanzar.

## Limitaciones honestas

- No hay todavía un harness que corra la suite contra varias
  configuraciones seguidas y tabule los resultados uno al lado del otro --
  hoy hay que cambiar `.env` y relanzar a mano entre modelo y modelo,
  guardando el informe aparte cada vez (ver arriba). Si el volumen de
  comparaciones crece, vale la pena automatizarlo.
- Los flags de `--tool-call-parser` de la tabla de presets se han escrito
  a partir de la documentación pública de vLLM, no se han podido verificar
  en vivo contra una GPU real desde este entorno de desarrollo (sin acceso
  a la máquina en cuestión) -- el smoke test del paso 4 es precisamente la
  verificación real pendiente, la primera vez que se use cada preset.
- `provision_gpu_vm.sh` asume Ubuntu con el driver NVIDIA ya instalado
  (habitual en imágenes de máquina GPU de cualquier proveedor cloud) --
  instalar el driver desde cero no está cubierto, varía según el proveedor
  real de la máquina.
