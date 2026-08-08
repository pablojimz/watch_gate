"""Tests de protección CSRF (`state`) del flujo OAuth de GitHub del Dashboard.

Caso real encontrado en revisión: `github_login`/`github_callback` no
generaban ni validaban ningún `state` -- un atacante podía iniciar el flujo
con su propia cuenta de GitHub, capturar el `code`, y hacer que la víctima
visitara el callback con ese código (login CSRF): el navegador de la
víctima terminaba con una sesión de WatchGate vinculada a la identidad
GitHub del atacante.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from watchgate.dashboard.backend.auth import _OAUTH_STATE_COOKIE
from watchgate.dashboard.backend.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("WATCHGATE_GITHUB_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("WATCHGATE_GITHUB_CLIENT_SECRET", "test-client-secret")
    return TestClient(app)


def test_github_login_sets_state_cookie_and_includes_it_in_redirect(client: TestClient) -> None:
    response = client.get("/api/auth/github/login", follow_redirects=False)

    assert response.status_code == 307
    location = response.headers["location"]
    assert "state=" in location

    state_in_url = location.split("state=", 1)[1].split("&", 1)[0]
    assert response.cookies[_OAUTH_STATE_COOKIE] == state_in_url


def test_github_callback_rejects_missing_state_cookie(client: TestClient) -> None:
    """El callback recibe `state` en la query, pero la cookie que debería
    haberse fijado en /login nunca llegó (o expiró) -- debe rechazarse."""
    response = client.get(
        "/api/auth/github/callback",
        params={"code": "attacker-code", "state": "cualquier-cosa"},
    )
    assert response.status_code == 400
    assert "state" in response.json()["detail"].lower()


def test_github_callback_rejects_mismatched_state(client: TestClient) -> None:
    """Escenario del ataque real: el atacante fabrica su propia cookie/state
    (o la víctima trae un state de una sesión de login distinta) -- si no
    coincide con el `state` de la query, se rechaza."""
    client.cookies.set(_OAUTH_STATE_COOKIE, "state-legitimo-de-la-victima")
    response = client.get(
        "/api/auth/github/callback",
        params={"code": "attacker-code", "state": "state-del-atacante"},
    )
    assert response.status_code == 400


def test_github_callback_accepts_matching_state_and_completes_login(client: TestClient) -> None:
    login_resp = client.get("/api/auth/github/login", follow_redirects=False)
    state = login_resp.cookies[_OAUTH_STATE_COOKIE]

    with patch("watchgate.dashboard.backend.auth.httpx.post") as mock_post, patch(
        "watchgate.dashboard.backend.auth.httpx.get"
    ) as mock_get:
        mock_post.return_value.raise_for_status = lambda: None
        mock_post.return_value.json.return_value = {"access_token": "gho_faketoken"}
        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json.return_value = {"login": "alice"}

        response = client.get(
            "/api/auth/github/callback",
            params={"code": "real-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert "watchgate_session" in response.cookies
    # La cookie de state de un solo uso se limpia tras consumirse.
    assert response.cookies.get(_OAUTH_STATE_COOKIE) in (None, "")
