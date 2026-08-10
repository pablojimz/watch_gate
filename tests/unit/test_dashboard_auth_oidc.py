"""Tests unitarios para la autenticación OIDC (watchgate/dashboard/backend/auth_oidc.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

from watchgate.dashboard.backend import auth_oidc


@pytest.fixture
def oidc_app():
    app = FastAPI()
    app.include_router(auth_oidc.router, prefix="/api")
    return app


def test_oidc_endpoints_return_501_when_not_configured(oidc_app, monkeypatch):
    monkeypatch.delenv("WATCHGATE_OIDC_CLIENT_ID", raising=False)
    monkeypatch.delenv("WATCHGATE_OIDC_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("WATCHGATE_OIDC_ISSUER", raising=False)

    client = TestClient(oidc_app)

    resp_login = client.get("/api/auth/oidc/login")
    assert resp_login.status_code == 501
    assert "OIDC no configurado" in resp_login.json()["detail"]

    resp_callback = client.get("/api/auth/oidc/callback")
    assert resp_callback.status_code == 501
    assert "OIDC no configurado" in resp_callback.json()["detail"]


def test_setup_oidc_registers_client(monkeypatch):
    monkeypatch.setenv("WATCHGATE_OIDC_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("WATCHGATE_OIDC_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("WATCHGATE_OIDC_ISSUER", "https://keycloak.example.com/auth/realms/master")

    with patch.object(auth_oidc.oauth, "register") as mock_register:
        auth_oidc.setup_oidc()
        mock_register.assert_called_once_with(
            name="oidc",
            client_id="test-client-id",
            client_secret="test-client-secret",
            server_metadata_url="https://keycloak.example.com/auth/realms/master/.well-known/openid-configuration",
            client_kwargs={"scope": "openid profile email"},
        )


def test_oidc_login_redirects_when_configured(oidc_app, monkeypatch):
    monkeypatch.setenv("WATCHGATE_OIDC_CLIENT_ID", "test-client")
    monkeypatch.setenv("WATCHGATE_OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("WATCHGATE_OIDC_ISSUER", "https://keycloak.example.com/auth/realms/test")

    mock_client = MagicMock()
    mock_redirect = AsyncMock()
    mock_redirect.return_value = RedirectResponse(url="https://keycloak.example.com/auth", status_code=307)
    mock_client.authorize_redirect = mock_redirect

    with patch.object(auth_oidc.oauth, "create_client", return_value=mock_client):
        client = TestClient(oidc_app, follow_redirects=False)
        resp = client.get("/api/auth/oidc/login")
        assert resp.status_code == 307
        assert "location" in resp.headers


def test_oidc_callback_success_sets_session_cookie(oidc_app, monkeypatch):
    monkeypatch.setenv("WATCHGATE_OIDC_CLIENT_ID", "test-client")
    monkeypatch.setenv("WATCHGATE_OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("WATCHGATE_OIDC_ISSUER", "https://keycloak.example.com/auth/realms/test")

    mock_client = MagicMock()
    mock_token = AsyncMock()
    mock_token.return_value = {
        "userinfo": {"preferred_username": "oidc_alice", "email": "alice@example.com"}
    }
    mock_client.authorize_access_token = mock_token

    with patch.object(auth_oidc.oauth, "create_client", return_value=mock_client):
        client = TestClient(oidc_app, follow_redirects=False)
        resp = client.get("/api/auth/oidc/callback?code=test-code")
        assert resp.status_code == 307
        assert "watchgate_session" in resp.headers.get("set-cookie", "")
        assert resp.headers["location"].endswith("/repos")


def test_oidc_callback_raises_400_when_no_login_in_userinfo(oidc_app, monkeypatch):
    monkeypatch.setenv("WATCHGATE_OIDC_CLIENT_ID", "test-client")
    monkeypatch.setenv("WATCHGATE_OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("WATCHGATE_OIDC_ISSUER", "https://keycloak.example.com/auth/realms/test")

    mock_client = MagicMock()
    mock_token = AsyncMock()
    mock_token.return_value = {"userinfo": {}}
    mock_client.authorize_access_token = mock_token

    with patch.object(auth_oidc.oauth, "create_client", return_value=mock_client):
        client = TestClient(oidc_app)
        resp = client.get("/api/auth/oidc/callback?code=test-code")
        assert resp.status_code == 400
        assert "OIDC no devolvió identificador" in resp.json()["detail"]
