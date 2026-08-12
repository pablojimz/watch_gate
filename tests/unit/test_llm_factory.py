"""Tests de watchgate/core/layers/_semantic/llm_factory.py (§7.3)."""

from __future__ import annotations

import pytest

from watchgate.core.layers._semantic.client import AnthropicClient
from watchgate.core.layers._semantic.llm_factory import build_llm_client
from watchgate.core.layers._semantic.llm_providers import GeminiClient, OpenAICompatibleClient


def test_defaults_to_anthropic_when_nothing_is_configured(monkeypatch):
    monkeypatch.delenv("WATCHGATE_LLM_PROVIDER", raising=False)
    client = build_llm_client()
    assert isinstance(client, AnthropicClient)
    assert client._model == "claude-sonnet-5"


def test_reads_provider_from_environment(monkeypatch):
    monkeypatch.setenv("WATCHGATE_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("WATCHGATE_LLM_API_KEY", "fake-key")
    client = build_llm_client()
    assert isinstance(client, GeminiClient)
    assert client._model == "gemini-3.6-flash"


def test_explicit_provider_argument_overrides_environment(monkeypatch):
    monkeypatch.setenv("WATCHGATE_LLM_PROVIDER", "gemini")
    client = build_llm_client(provider="anthropic")
    assert isinstance(client, AnthropicClient)


def test_local_provider_uses_default_ollama_base_url(monkeypatch):
    monkeypatch.setenv("WATCHGATE_LLM_PROVIDER", "local")
    monkeypatch.delenv("WATCHGATE_LLM_BASE_URL", raising=False)
    client = build_llm_client()
    assert isinstance(client, OpenAICompatibleClient)
    assert client._base_url == "http://localhost:11434/v1"
    assert client._model == "llama3.1"


def test_local_provider_respects_custom_base_url_and_model(monkeypatch):
    monkeypatch.setenv("WATCHGATE_LLM_PROVIDER", "local")
    monkeypatch.setenv("WATCHGATE_LLM_BASE_URL", "http://mi-servidor:8080/v1")
    monkeypatch.setenv("WATCHGATE_LLM_MODEL", "qwen2.5-coder")
    client = build_llm_client()
    assert client._base_url == "http://mi-servidor:8080/v1"
    assert client._model == "qwen2.5-coder"


def test_unknown_provider_raises_a_clear_error(monkeypatch):
    monkeypatch.setenv("WATCHGATE_LLM_PROVIDER", "cohere")
    with pytest.raises(ValueError, match="Proveedor LLM desconocido"):
        build_llm_client()


def test_gemini_key_with_default_anthropic_provider_raises_a_clear_error(monkeypatch):
    """Regresión, reproducida: WATCHGATE_LLM_API_KEY con una clave real de
    Gemini (prefijo AIzaSy) pero sin WATCHGATE_LLM_PROVIDER (por defecto
    "anthropic") construía un AnthropicClient con esa clave -- fallaba con un
    error de autenticación genérico contra la API de Anthropic, "la misma
    clave" que el usuario sabe que es correcta, solo que para el proveedor
    equivocado. Ahora debe fallar aquí, con un mensaje que señale el
    desajuste, en vez de mucho más tarde con un 401 opaco."""
    monkeypatch.delenv("WATCHGATE_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("WATCHGATE_LLM_API_KEY", "AIzaSyD-fake-gemini-key-1234567890abcd")

    with pytest.raises(ValueError, match="formato de una clave de 'gemini'"):
        build_llm_client()


def test_anthropic_key_with_gemini_provider_raises_a_clear_error(monkeypatch):
    monkeypatch.setenv("WATCHGATE_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("WATCHGATE_LLM_API_KEY", "sk-ant-api03-fake-key-1234567890")

    with pytest.raises(ValueError, match="formato de una clave de 'anthropic'"):
        build_llm_client()


def test_key_with_unrecognized_format_does_not_block_construction(monkeypatch):
    """Una clave que no coincide con ningún prefijo conocido (proxy interno,
    clave de empresa con formato propio, etc.) no debe bloquearse -- solo se
    detectan desajustes cuando hay una señal fiable, no la ausencia de una."""
    monkeypatch.setenv("WATCHGATE_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("WATCHGATE_LLM_API_KEY", "unrecognized-format-key")

    client = build_llm_client()

    assert isinstance(client, AnthropicClient)
