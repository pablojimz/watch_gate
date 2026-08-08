"""Tests unitarios para la capa de datos Multi-Tenant y aislada por Organización."""

from __future__ import annotations

from sqlmodel import Session, create_engine

from watchgate.core.models import AggregatedResult, LayerResult, Semaforo
from watchgate.db.connection import init_db
from watchgate.db.models import Organization
from watchgate.db.repository import (
    create_api_key,
    create_organization,
    create_user,
    get_organization,
    get_semantic_cache,
    get_token_usage,
    record_token_usage,
    save_pr_score,
    set_semantic_cache,
    verify_api_key,
)


def _get_memory_session() -> Session:
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    init_db(test_engine)
    return Session(test_engine)


def test_create_and_get_organization() -> None:
    session = _get_memory_session()
    org = create_organization(
        session, name="Acme Corp", plan_tier="pro", monthly_token_quota=5_000_000
    )

    assert isinstance(org, Organization)
    assert org.name == "Acme Corp"
    assert org.plan_tier == "pro"
    assert org.monthly_token_quota == 5_000_000

    fetched = get_organization(session, org.id)
    assert fetched is not None
    assert fetched.id == org.id
    assert fetched.name == "Acme Corp"


def test_create_user_never_silently_reassigns_existing_org() -> None:
    """Caso real encontrado en revisión: `create_user` reescribía en
    silencio el `org_id` de un usuario ya existente (mismo email) si se le
    pasaba uno distinto, sin ninguna comprobación de autorización. Con
    `User.email` único a nivel global, esto era una vía para que un
    segundo tenant "robara" la afiliación de organización de un usuario ya
    existente. Un `org_id` distinto en una llamada posterior debe
    ignorarse -- solo se rellena si el usuario todavía no tenía uno."""
    session = _get_memory_session()
    org_a = create_organization(session, name="Org A")
    org_b = create_organization(session, name="Org B")

    user = create_user(session, email="shared@example.com", name="Shared", org_id=org_a.id)
    assert user.org_id == org_a.id

    # Un segundo "tenant" intenta reclamar el mismo email con otra org.
    same_user = create_user(session, email="shared@example.com", name="Shared", org_id=org_b.id)
    assert same_user.id == user.id
    assert same_user.org_id == org_a.id  # NO se reasignó a org_b


def test_create_user_fills_in_missing_org_id() -> None:
    """Caso legítimo distinto del anterior: un usuario existente que
    todavía no tenía ninguna organización SÍ debe poder completarla."""
    session = _get_memory_session()
    org = create_organization(session, name="Org A")

    user = create_user(session, email="noorg@example.com", name="No Org")
    assert user.org_id is None

    updated = create_user(session, email="noorg@example.com", name="No Org", org_id=org.id)
    assert updated.org_id == org.id


def test_user_and_api_key_with_organization() -> None:
    session = _get_memory_session()
    org = create_organization(session, name="CyberSec Org")
    user = create_user(session, email="sec@cybersec.com", name="Sec Lead", org_id=org.id)

    assert user.org_id == org.id

    key_record, raw_token = create_api_key(
        session,
        user_id=user.id,
        org_id=org.id,
        default_agent_name="code-reviewer-bot",
        name="CI Bot Key",
    )

    assert key_record.org_id == org.id
    assert key_record.default_agent_name == "code-reviewer-bot"

    verified = verify_api_key(session, raw_token)
    assert verified is not None
    verified_key, verified_user, verified_org = verified

    assert verified_key.id == key_record.id
    assert verified_user.id == user.id
    assert verified_org is not None
    assert verified_org.id == org.id
    assert verified_org.name == "CyberSec Org"


def test_multitenant_token_usage() -> None:
    session = _get_memory_session()
    org1 = create_organization(session, name="Org Alpha")
    org2 = create_organization(session, name="Org Beta")

    user1 = create_user(session, email="u1@alpha.com", name="User 1", org_id=org1.id)
    user2 = create_user(session, email="u2@beta.com", name="User 2", org_id=org2.id)

    # Imputar consumo a org1
    record_token_usage(session, user1.id, tokens_used=5000, month="2026-08", org_id=org1.id)
    record_token_usage(session, user1.id, tokens_used=3000, month="2026-08", org_id=org1.id)

    # Imputar consumo a org2
    record_token_usage(session, user2.id, tokens_used=2000, month="2026-08", org_id=org2.id)

    # Verificar consultas por org_id
    assert get_token_usage(session, month="2026-08", org_id=org1.id) == 8000
    assert get_token_usage(session, month="2026-08", org_id=org2.id) == 2000


def test_semantic_cache_multitenant_isolation() -> None:
    session = _get_memory_session()
    org1_id = "org-111"
    org2_id = "org-222"
    diff_hash = "shared_diff_hash_999"

    # Guardar entrada de caché para Org 1
    set_semantic_cache(
        session, diff_hash_value=diff_hash, output_json='{"risk": "high"}', org_id=org1_id
    )

    # La Org 1 la encuentra
    cached_org1 = get_semantic_cache(session, diff_hash_value=diff_hash, org_id=org1_id)
    assert cached_org1 == '{"risk": "high"}'

    # La Org 2 NO debe poder leer la caché de la Org 1
    cached_org2 = get_semantic_cache(session, diff_hash_value=diff_hash, org_id=org2_id)
    assert cached_org2 is None


def test_save_pr_score_with_org_and_agent() -> None:
    session = _get_memory_session()
    org = create_organization(session, name="DevOps Org")
    user = create_user(session, email="dev@devops.com", name="Dev", org_id=org.id)

    aggregated = AggregatedResult(
        score=10,
        semaforo=Semaforo.VERDE,
        layer_results={
            "static": LayerResult(layer_name="static", risk_score=10, justification="clean")
        },
        weights_used={"static": 1.0},
        pr_id="101",
        repo="devops/repo",
        timestamp="2026-08-07T10:00:00Z",
    )

    score_rec = save_pr_score(
        session,
        aggregated_result=aggregated,
        user_id=user.id,
        org_id=org.id,
        agent_id="agent-v1-opencode",
    )

    assert score_rec.org_id == org.id
    assert score_rec.agent_id == "agent-v1-opencode"
    assert score_rec.repo == "devops/repo"
