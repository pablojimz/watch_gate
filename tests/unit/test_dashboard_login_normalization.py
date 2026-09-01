"""Tests de normalize_login (spec §13): un login no debe poder duplicarse
por may/min o espacios -- "Alice", "alice" y " alice " son el mismo usuario
en todo el dashboard (login local, dev-login, asignación de roles).
"""

from __future__ import annotations

import pytest

from watchgate.dashboard.backend import db as database
from watchgate.dashboard.backend.schemas import (
    DevLoginIn,
    PasswordLoginIn,
    RepoRoleIn,
    normalize_login,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Alice", "alice"),
        (" alice ", "alice"),
        ("ALICE", "alice"),
        ("  Bob-Dev  ", "bob-dev"),
    ],
)
def test_normalize_login_canonical_form(raw: str, expected: str) -> None:
    assert normalize_login(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "\t"])
def test_normalize_login_rejects_empty(raw: str) -> None:
    with pytest.raises(ValueError, match="vacío"):
        normalize_login(raw)


def test_repo_role_in_normalizes_user_login() -> None:
    body = RepoRoleIn(user_login="  Alice  ", repo="acme/payments-api", role="revisor")
    assert body.user_login == "alice"


def test_dev_login_in_normalizes_login() -> None:
    assert DevLoginIn(login="ALICE").login == "alice"


def test_password_login_in_normalizes_username() -> None:
    assert PasswordLoginIn(username=" Alice ", password="x").username == "alice"


def test_upsert_role_does_not_duplicate_by_case(tmp_path) -> None:
    db_path = tmp_path / "dashboard.db"
    with database.db_session(db_path) as conn:
        database.upsert_role(conn, "Alice", "acme/payments-api", "mantenedor")
        database.upsert_role(conn, "alice", "acme/payments-api", "revisor")
        database.upsert_role(conn, " ALICE ", "acme/payments-api", "mantenedor")

        roles = database.list_roles(conn, "acme/payments-api")
        assert len(roles) == 1
        assert roles[0]["user_login"] == "alice"
        assert roles[0]["role"] == "mantenedor"  # la última escritura gana


def test_get_and_delete_role_are_case_insensitive(tmp_path) -> None:
    db_path = tmp_path / "dashboard.db"
    with database.db_session(db_path) as conn:
        database.upsert_role(conn, "alice", "acme/payments-api", "revisor")

        assert database.get_role(conn, "Alice", "acme/payments-api") == "revisor"
        assert database.delete_role(conn, "  ALICE  ", "acme/payments-api") is True
        assert database.get_role(conn, "alice", "acme/payments-api") is None


def test_authenticate_user_is_case_insensitive(tmp_path) -> None:
    db_path = tmp_path / "dashboard.db"
    with database.db_session(db_path) as conn:
        database.upsert_user(conn, "Alice", "secreto123", "Alice Demo")

        assert database.authenticate_user(conn, "alice", "secreto123") is True
        assert database.authenticate_user(conn, "ALICE", "secreto123") is True
        assert database.authenticate_user(conn, "alice", "mal") is False
