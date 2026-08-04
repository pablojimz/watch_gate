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
    assert client._model == "gemini-2.5-flash"


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
