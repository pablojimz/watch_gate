"""Tests de watchgate/api/auth.py (resolución de API key -> Organización)."""

from __future__ import annotations

from sqlmodel import Session, create_engine

from watchgate.api.auth import _FALLBACK_ORG_ID, get_current_user_from_api_key
from watchgate.db.connection import init_db
from watchgate.db.repository import create_api_key, create_user, get_organization


def _session(tmp_path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'auth.db'}", connect_args={"check_same_thread": False}
    )
    init_db(engine)
    return Session(engine)


def test_api_key_without_org_falls_back_to_a_persisted_default_org(tmp_path):
    """Caso real encontrado en revisión: antes, una API key sin `org_id`
    propio (caso legado -- creada fuera del flujo del Dashboard, que ya
    provisiona una Organización real por usuario) hacía que `auth.py`
    fabricara un `Organization(...)` EN MEMORIA, nunca persistido.
    `QuotaService`/`PolicyService` vuelven a buscarla por id y, al no
    existir la fila, la cuota caía a un valor por defecto sin aplicar de
    verdad y la gobernanza corporativa se saltaba en silencio. Ahora debe
    quedar persistida de verdad la primera vez que hace falta."""
    session = _session(tmp_path)
    user = create_user(session, email="legacy@example.com", name="Legacy User")
    # Simula una clave creada fuera del flujo del Dashboard, sin org_id.
    _api_key, raw_token = create_api_key(
        session, user_id=user.id, org_id=None, monitored_repo_id="test-repo-id"
    )

    result = get_current_user_from_api_key(
        bearer=None,
        header_key=raw_token,
        session=session,
    )
    _api_key_out, _user_out, org = result

    assert org is not None
    assert org.id == _FALLBACK_ORG_ID
    # No es un objeto fabricado en memoria -- una consulta nueva a la BD
    # debe encontrar la misma fila.
    persisted = get_organization(session, _FALLBACK_ORG_ID)
    assert persisted is not None
    assert persisted.id == org.id


def test_api_key_without_org_reuses_the_same_persisted_default_org(tmp_path):
    """Dos claves distintas sin `org_id` propio deben caer en la MISMA fila
    persistida (get-or-create idempotente), no crear una nueva cada vez."""
    session = _session(tmp_path)
    user1 = create_user(session, email="legacy1@example.com", name="Legacy1")
    user2 = create_user(session, email="legacy2@example.com", name="Legacy2")
    _key1, token1 = create_api_key(
        session, user_id=user1.id, org_id=None, monitored_repo_id="test-repo-id-1"
    )
    _key2, token2 = create_api_key(
        session, user_id=user2.id, org_id=None, monitored_repo_id="test-repo-id-2"
    )

    _, _, org1 = get_current_user_from_api_key(bearer=None, header_key=token1, session=session)
    _, _, org2 = get_current_user_from_api_key(bearer=None, header_key=token2, session=session)

    assert org1.id == org2.id == _FALLBACK_ORG_ID
