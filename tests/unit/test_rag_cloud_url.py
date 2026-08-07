"""Tests unitarios para la instanciación de ChromaDB en modo RAG distribuido en la nube."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

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
                host="chroma.internal", port=8000, ssl=False
            )
            assert client is not None
