"""Tests de watchgate/dashboard/backend/auth.py: cifrado de la cookie de sesión.

Caso real encontrado en revisión: `create_session_token` puede embeber un
token de acceso de GitHub real (scope `repo,read:org`) en el payload de la
cookie de sesión. Antes esto era un JWT firmado (JWS) pero NO cifrado --
cualquiera que leyera el valor crudo de la cookie (fuera de la red: un HAR
compartido en un bug report, logs de un proxy que registre `Set-Cookie`,
etc.) podía decodificar el payload en base64 sin necesitar el secreto y
obtener el token de GitHub vivo. Ahora es un JWT anidado: firmado y encima
cifrado (AES-256-GCM) con una clave derivada del mismo secreto de sesión.
"""

from __future__ import annotations

import pytest
from jose.exceptions import JOSEError

from watchgate.dashboard.backend.auth import create_session_token, decode_session_token


@pytest.fixture(autouse=True)
def _session_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WATCHGATE_DASHBOARD_SECRET", "un-secreto-de-test-largo-de-verdad-32")


def test_session_token_does_not_leak_github_token_in_plaintext() -> None:
    raw_github_token = "gho_liveGitHubAccessTokenWithRepoScope123"
    token = create_session_token("alice", github_token=raw_github_token)

    # Ni el token de GitHub en claro, ni siquiera su forma en base64 (lo que
    # bastaría para leerlo de un JWS sin cifrar), deben aparecer en el
    # valor de la cookie.
    assert raw_github_token not in token


def test_session_token_roundtrips_with_correct_secret() -> None:
    token = create_session_token("alice", github_token="gho_sometoken")
    payload = decode_session_token(token)
    assert payload["sub"] == "alice"
    assert payload["gh"] == "gho_sometoken"


def test_session_token_rejects_tampered_ciphertext() -> None:
    token = create_session_token("alice")
    tampered = token[:-4] + ("A" if token[-4] != "A" else "B") + token[-3:]
    with pytest.raises(JOSEError):
        decode_session_token(tampered)


def test_session_token_undecryptable_without_matching_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = create_session_token("alice", github_token="gho_sometoken")

    monkeypatch.setenv("WATCHGATE_DASHBOARD_SECRET", "un-secreto-completamente-distinto-32chars")
    with pytest.raises(JOSEError):
        decode_session_token(token)
