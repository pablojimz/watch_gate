"""Tests del adaptador de GitHub App (watchgate/adapters/github_app.py).

Sin red: httpx se monkeypatchea. La firma RS256 sí es real -- se genera un
par de claves RSA efímero con `cryptography` (ya dependencia del proyecto)
y se verifica el JWT con la clave pública, no con mocks.
"""

from __future__ import annotations

from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt as jose_jwt

from watchgate.adapters import github_app


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("WATCHGATE_GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("WATCHGATE_GITHUB_APP_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("WATCHGATE_GITHUB_APP_PRIVATE_KEY_PATH", raising=False)
    github_app._installation_token_cache.clear()
    yield
    github_app._installation_token_cache.clear()


@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


class _FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        pass

    def json(self) -> Any:
        return self._payload


def test_not_configured_returns_none_without_any_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        github_app.httpx, "post", lambda *a, **k: pytest.fail("no debe llamar a la red")
    )
    assert github_app.github_app_configured() is False
    assert github_app.generate_app_jwt() is None
    assert github_app.get_installation_token("123") is None


def test_app_jwt_signs_rs256_and_verifies_with_public_key(
    monkeypatch: pytest.MonkeyPatch, rsa_keypair: tuple[str, str]
) -> None:
    private_pem, public_pem = rsa_keypair
    monkeypatch.setenv("WATCHGATE_GITHUB_APP_ID", "987654")
    monkeypatch.setenv("WATCHGATE_GITHUB_APP_PRIVATE_KEY", private_pem)

    token = github_app.generate_app_jwt()
    assert token is not None
    claims = jose_jwt.decode(token, public_pem, algorithms=["RS256"])
    assert claims["iss"] == "987654"
    assert claims["exp"] > claims["iat"]


def test_private_key_accepts_escaped_newlines(
    monkeypatch: pytest.MonkeyPatch, rsa_keypair: tuple[str, str]
) -> None:
    """Un PEM pegado en una variable de entorno suele llegar con '\\n'
    literales en vez de saltos de línea reales."""
    private_pem, public_pem = rsa_keypair
    monkeypatch.setenv("WATCHGATE_GITHUB_APP_ID", "987654")
    monkeypatch.setenv("WATCHGATE_GITHUB_APP_PRIVATE_KEY", private_pem.replace("\n", "\\n"))

    token = github_app.generate_app_jwt()
    assert token is not None
    assert jose_jwt.decode(token, public_pem, algorithms=["RS256"])["iss"] == "987654"


def test_installation_token_is_cached_per_process(
    monkeypatch: pytest.MonkeyPatch, rsa_keypair: tuple[str, str]
) -> None:
    private_pem, _ = rsa_keypair
    monkeypatch.setenv("WATCHGATE_GITHUB_APP_ID", "987654")
    monkeypatch.setenv("WATCHGATE_GITHUB_APP_PRIVATE_KEY", private_pem)

    calls: list[str] = []

    def _fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        calls.append(url)
        assert "/app/installations/555/access_tokens" in url
        assert kwargs["headers"]["Authorization"].startswith("Bearer ")
        return _FakeResponse({"token": "ghs_efimero"})

    monkeypatch.setattr(github_app.httpx, "post", _fake_post)

    assert github_app.get_installation_token("555") == "ghs_efimero"
    assert github_app.get_installation_token("555") == "ghs_efimero"
    assert len(calls) == 1, "la segunda llamada debe servirse de la caché"


def test_list_installation_repositories_returns_full_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(github_app, "get_installation_token", lambda installation_id: "ghs_x")

    def _fake_get(url: str, **kwargs: Any) -> _FakeResponse:
        assert url.endswith("/installation/repositories")
        return _FakeResponse(
            {
                "repositories": [
                    {"full_name": "acme/uno"},
                    {"full_name": "acme/dos"},
                ]
            }
        )

    monkeypatch.setattr(github_app.httpx, "get", _fake_get)
    assert github_app.list_installation_repositories("555") == ["acme/uno", "acme/dos"]


def test_list_installation_repositories_degrades_to_empty_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(github_app, "get_installation_token", lambda installation_id: None)
    assert github_app.list_installation_repositories("555") == []
