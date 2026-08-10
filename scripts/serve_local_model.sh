#!/usr/bin/env bash
# Sirve un modelo local vía vLLM con un endpoint de chat completions
# compatible con OpenAI, con tool calling habilitado -- ver
# docs/despliegue_gpu_modelos_locales.md para el porqué de cada preset y
# cómo apuntar WatchGate al servidor resultante.
#
# Uso:
#   ./scripts/serve_local_model.sh <preset>
#   ./scripts/serve_local_model.sh <model-id-de-huggingface> <tool-call-parser>
#
# Presets disponibles: llama3.1-8b, qwen2.5-14b, qwen2.5-32b-awq
#
# Para un model-id no listado como preset, hay que pasar también el
# --tool-call-parser correcto a mano (segundo argumento) -- consultar
# `vllm serve --help` en la propia máquina para la lista de parsers que
# soporta la versión instalada; los nombres han cambiado entre versiones
# de vLLM, así que los presets de abajo pueden quedar desactualizados.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -d ".venv-vllm" ]; then
  echo "ERROR: .venv-vllm/ no existe -- corre primero ./scripts/provision_gpu_vm.sh" >&2
  exit 1
fi

PRESET="${1:-}"
if [ -z "$PRESET" ]; then
  echo "Uso: $0 <preset|model-id-de-huggingface> [tool-call-parser]" >&2
  echo "Presets: llama3.1-8b, qwen2.5-14b, qwen2.5-32b-awq" >&2
  exit 1
fi

MODEL=""
PARSER=""
EXTRA_FLAGS=()

case "$PRESET" in
  llama3.1-8b)
    MODEL="meta-llama/Llama-3.1-8B-Instruct"
    PARSER="llama3_json"
    ;;
  qwen2.5-14b)
    MODEL="Qwen/Qwen2.5-14B-Instruct"
    PARSER="hermes"
    ;;
  qwen2.5-32b-awq)
    MODEL="Qwen/Qwen2.5-32B-Instruct-AWQ"
    PARSER="hermes"
    EXTRA_FLAGS+=(--quantization awq)
    ;;
  *)
    # No es un preset conocido: se trata como un model-id de HuggingFace
    # directo. El segundo argumento (--tool-call-parser) es obligatorio en
    # ese caso -- sin él, el servidor arranca pero el tool calling falla en
    # silencio de formas raras (ver nota en el documento de despliegue).
    MODEL="$PRESET"
    PARSER="${2:-}"
    if [ -z "$PARSER" ]; then
      echo "ERROR: '$PRESET' no es un preset conocido (llama3.1-8b, qwen2.5-14b," >&2
      echo "qwen2.5-32b-awq) -- para un model-id de HuggingFace directo hace falta" >&2
      echo "pasar también el --tool-call-parser correcto como segundo argumento." >&2
      echo "Consultar 'vllm serve --help' en esta máquina para los valores válidos." >&2
      exit 1
    fi
    ;;
esac

echo "==> Modelo: $MODEL"
echo "==> Tool-call parser: $PARSER"
echo "==> Endpoint: http://localhost:8000/v1"
echo "==> (WATCHGATE_LLM_MODEL debe ser exactamente '$MODEL' en tu .env)"
echo

# shellcheck disable=SC1091
source .venv-vllm/bin/activate
exec vllm serve "$MODEL" \
  --port 8000 \
  --enable-auto-tool-choice \
  --tool-call-parser "$PARSER" \
  "${EXTRA_FLAGS[@]}"
