"""Fábrica del cliente LLM configurable por entorno (§7.3).

`layer.py` no necesita saber qué proveedor hay detrás: `build_llm_client()`
lee `WATCHGATE_LLM_PROVIDER` y devuelve la implementación de `LLMClient`
correspondiente -- Anthropic (por defecto), Gemini, o un modelo local servido
por cualquier motor compatible con la API de chat de OpenAI (Ollama,
llama.cpp server, LM Studio, vLLM...). Cambiar de proveedor es una variable
de entorno, no un cambio de código.
"""

from __future__ import annotations

import os

from watchgate.core.layers._semantic.client import AnthropicClient, LLMClient
from watchgate.core.layers._semantic.llm_providers import GeminiClient, OpenAICompatibleClient

_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5",
    "gemini": "gemini-2.5-flash",
    "local": "llama3.1",
}
# Puerto/ruta por defecto de Ollama sirviendo su API compatible con OpenAI.
_DEFAULT_LOCAL_BASE_URL = "http://localhost:11434/v1"


def build_llm_client(provider: str | None = None) -> LLMClient:
    """Construye el `LLMClient` configurado.

    `provider` explícito tiene prioridad; si no se pasa, se lee de
    `WATCHGATE_LLM_PROVIDER` (por defecto "anthropic"). El modelo concreto se
    puede forzar con `WATCHGATE_LLM_MODEL`; si no, cada proveedor usa un
    valor por defecto razonable. Para "local", `WATCHGATE_LLM_BASE_URL` fija
    el servidor (por defecto, el de Ollama en localhost).
    """
    resolved_provider = provider or os.environ.get("WATCHGATE_LLM_PROVIDER", "anthropic")
    if resolved_provider not in _DEFAULT_MODELS:
        raise ValueError(
            f"Proveedor LLM desconocido: {resolved_provider!r}. Valores válidos: "
            f"{', '.join(_DEFAULT_MODELS)}."
        )
    model = os.environ.get("WATCHGATE_LLM_MODEL") or _DEFAULT_MODELS[resolved_provider]

    if resolved_provider == "anthropic":
        return AnthropicClient(model=model)
    if resolved_provider == "gemini":
        return GeminiClient(model=model)

    base_url = os.environ.get("WATCHGATE_LLM_BASE_URL", _DEFAULT_LOCAL_BASE_URL)
    api_key = (
        os.environ.get("WATCHGATE_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
    )
    return OpenAICompatibleClient(base_url=base_url, model=model, api_key=api_key)
