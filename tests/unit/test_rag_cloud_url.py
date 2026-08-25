"""Tests unitarios para la instanciación de ChromaDB en modo RAG distribuido en la nube."""

from __future__ import annotations

import os
from unittest.mock import ANY, MagicMock, patch

from watchgate.core.rag.indexer import get_chroma_client


def test_get_chroma_client_local(tmp_path):
    index_dir = str(tmp_path / "rag_index")

    with patch.dict(os.environ, {}, clear=True):
        client = get_chroma_client(index_path=index_dir)
        # Debe retornar un PersistentClient
        assert hasattr(client, "get_or_create_collection") or hasattr(client, "create_collection")


def test_get_chroma_client_cloud_url():
    cloud_url = "http://chroma.internal:8000"

    with patch.dict(os.environ, {"WATCHGATE_CHROMA_URL": cloud_url}):
        with patch("chromadb.HttpClient") as mock_http_client:
            mock_http_client.return_value = MagicMock()

            client = get_chroma_client()

            mock_http_client.assert_called_once_with(
                host="chroma.internal", port=8000, ssl=False, settings=ANY
            )
            assert client is not None


def test_get_chroma_client_disables_telemetry():
    """`anonymized_telemetry=False` en ambos clientes (local y remoto) --
    hallazgo real: sin esto, el wrapper interno de telemetría de ChromaDB
    (posthog) revienta con un error real de compatibilidad de versión
    ("capture() takes 1 positional argument but 3 were given") en CADA
    llamada a la capa semántica/RAG. Ver silence_noisy_third_party_loggers()
    en logging_config.py para la otra mitad del arreglo (por qué el filtro
    de nivel de log tampoco bastaba)."""
    with patch.dict(os.environ, {}, clear=True):
        with patch("chromadb.PersistentClient") as mock_persistent_client:
            mock_persistent_client.return_value = MagicMock()

            get_chroma_client(index_path="/tmp/does-not-matter")

            _, kwargs = mock_persistent_client.call_args
            assert kwargs["settings"].anonymized_telemetry is False
