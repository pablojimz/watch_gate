#!/usr/bin/env bash
# Provisiona una máquina Linux con GPU para correr WatchGate + un servidor
# de modelos local (vLLM) -- ver docs/despliegue_gpu_modelos_locales.md
# para el porqué de cada paso y cómo seguir después de este script.
#
# Idempotente: se puede volver a correr sin duplicar instalaciones.
# No asume ningún proveedor de nube concreto -- solo Linux + NVIDIA.
#
# Uso:
#   ./scripts/provision_gpu_vm.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Comprobando GPU NVIDIA..."
if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi no encontrado -- no hay driver NVIDIA instalado." >&2
  echo "Instalar el driver correcto depende de la imagen/proveedor concreto de la" >&2
  echo "máquina; fuera de alcance de este script genérico. Instalarlo primero y" >&2
  echo "volver a lanzar este script." >&2
  exit 1
fi
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

echo "==> Comprobando Python >=3.11..."
PYTHON_BIN=""
for candidate in python3.11 python3.12 python3.13 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    ver="$("$candidate" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
    major="${ver%%.*}"
    minor="${ver##*.}"
    if [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; then
      PYTHON_BIN="$candidate"
      break
    fi
  fi
done
if [ -z "$PYTHON_BIN" ]; then
  echo "ERROR: no se encontró Python >=3.11 (requires-python de pyproject.toml)." >&2
  echo "Instalar Python 3.11+ (p. ej. 'apt install python3.11 python3.11-venv' en" >&2
  echo "Ubuntu, o vía pyenv) y volver a lanzar este script." >&2
  exit 1
fi
echo "Usando $PYTHON_BIN ($("$PYTHON_BIN" --version))"

echo "==> Comprobando Poetry..."
if ! command -v poetry >/dev/null 2>&1; then
  echo "Instalando Poetry..."
  curl -sSL https://install.python-poetry.org | "$PYTHON_BIN" -
  export PATH="$HOME/.local/bin:$PATH"
fi
poetry --version

echo "==> poetry install (dependencias normales de WatchGate)..."
poetry env use "$PYTHON_BIN"
poetry install --no-interaction

# vLLM vive en un venv APARTE, nunca como dependencia de Poetry -- fija
# versiones muy concretas de torch/CUDA que casi seguro chocan con la
# versión de torch que ya trae sentence-transformers (RAG local, ver
# core/rag/indexer.py). Meterlo en el mismo entorno que gestiona
# poetry.lock arriesga con romper esa resolución para todo el mundo,
# incluida la gente que solo corre tests en un portátil sin GPU.
echo "==> Creando .venv-vllm/ (venv separado, solo para el servidor de inferencia)..."
if [ ! -d ".venv-vllm" ]; then
  "$PYTHON_BIN" -m venv .venv-vllm
fi
# shellcheck disable=SC1091
source .venv-vllm/bin/activate
pip install --upgrade pip --quiet
echo "==> Instalando vllm (puede tardar varios minutos, descarga CUDA + torch)..."
pip install vllm --quiet
deactivate

cat <<'EOF'

==> Provisión completa.

Siguientes pasos (ver docs/despliegue_gpu_modelos_locales.md para el detalle):

  1. Servir un modelo:
       ./scripts/serve_local_model.sh llama3.1-8b

  2. En otra terminal, configurar WatchGate para hablar con él:
       cp .env.example .env
       # editar .env: WATCHGATE_LLM_PROVIDER=local,
       # WATCHGATE_LLM_BASE_URL=http://localhost:8000/v1,
       # WATCHGATE_LLM_MODEL=<mismo model-id que serviste en el paso 1>

  3. Verificar que funciona de verdad (no solo "responde"):
       set -a && source .env && set +a
       poetry run python scripts/smoke_test_linea2.py --repo . --label primera-prueba

EOF
