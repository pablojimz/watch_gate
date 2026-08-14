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
    "gemini": "gemini-3.6-flash",
    "local": "llama3.1",
}
# Puerto/ruta por defecto de Ollama sirviendo su API compatible con OpenAI.
_DEFAULT_LOCAL_BASE_URL = "http://localhost:11434/v1"
# Un proveedor cloud (Anthropic/Gemini) responde de sobra en 60s -- el límite
# ahí es red, no cómputo. Un modelo local comparte GPU con lo que sea que
# corra al lado y el cuello de botella es cómputo puro: reproducido en vivo,
# qwen3.6:27b superaba los 60s en diffs grandes/con varias tool calls y la
# capa se marcaba "skipped" (timeout), no por peor razonamiento -- justo en
# los casos más difíciles, que es donde menos conviene perder la señal.
_DEFAULT_LOCAL_TIMEOUT_SECONDS = 120.0

# Prefijos de clave estables y documentados por cada proveedor (Anthropic
# siempre "sk-ant-", Google AI Studio siempre "AIzaSy") -- suficientes para
# detectar el error real, reproducido: WATCHGATE_LLM_API_KEY con una clave de
# Gemini pero WATCHGATE_LLM_PROVIDER sin poner (por defecto "anthropic")
# construye un AnthropicClient con esa clave, que falla con un error de
# autenticación genérico -- "la misma clave" que el usuario sabe que es
# correcta, solo que para el proveedor equivocado. Deliberadamente NO se
# intenta adivinar "local"/OpenAI: su formato de clave ("sk-...", sin más) lo
# comparten demasiados proveedores/proxies (OpenRouter, vLLM, etc.) para ser
# una señal fiable.
_KEY_PREFIX_HINTS: dict[str, str] = {
    "sk-ant-": "anthropic",
    "AIzaSy": "gemini",
}


def _guess_provider_from_key(api_key: str | None) -> str | None:
    if not api_key:
        return None
    for prefix, provider in _KEY_PREFIX_HINTS.items():
        if api_key.startswith(prefix):
            return provider
    return None


def _check_key_matches_provider(resolved_provider: str, api_key: str | None) -> None:
    guessed = _guess_provider_from_key(api_key)
    if guessed is not None and guessed != resolved_provider:
        raise ValueError(
            f"WATCHGATE_LLM_PROVIDER={resolved_provider!r}, pero WATCHGATE_LLM_API_KEY "
            f"tiene el formato de una clave de {guessed!r} (por su prefijo), no de "
            f"{resolved_provider!r}. ¿Falta poner WATCHGATE_LLM_PROVIDER={guessed!r}?"
        )


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
        _check_key_matches_provider(resolved_provider, os.environ.get("WATCHGATE_LLM_API_KEY"))
        return AnthropicClient(model=model)
    if resolved_provider == "gemini":
        gemini_key = os.environ.get("WATCHGATE_LLM_API_KEY") or os.environ.get("GEMINI_API_KEY")
        _check_key_matches_provider(resolved_provider, gemini_key)
        return GeminiClient(model=model)

    base_url = os.environ.get("WATCHGATE_LLM_BASE_URL", _DEFAULT_LOCAL_BASE_URL)
    api_key = (
        os.environ.get("WATCHGATE_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
    )
    timeout = float(
        os.environ.get("WATCHGATE_LLM_TIMEOUT_SECONDS", _DEFAULT_LOCAL_TIMEOUT_SECONDS)
    )
    return OpenAICompatibleClient(base_url=base_url, model=model, api_key=api_key, timeout=timeout)
