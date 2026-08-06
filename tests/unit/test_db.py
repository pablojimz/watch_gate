"""Tests unitarios para el paquete unificado de persistencia (watchgate/db/)."""

from __future__ import annotations

from sqlmodel import Session, create_engine

from watchgate.core.models import AggregatedResult, LayerResult, Semaforo
from watchgate.db.connection import init_db
from watchgate.db.models import User, UserAPIKey
from watchgate.db.repository import (
    create_api_key,
    create_user,
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


def test_init_db_creates_tables() -> None:
    session = _get_memory_session()
    assert session is not None


def test_create_user_and_api_key() -> None:
    session = _get_memory_session()
    user = create_user(session, email="alice@example.com", name="Alice Developer", role="mantenedor")

    assert isinstance(user, User)
    assert user.email == "alice@example.com"
    assert user.role == "mantenedor"

    key_record, raw_token = create_api_key(session, user_id=user.id, name="Test Key")

    assert isinstance(key_record, UserAPIKey)
    assert raw_token.startswith("wg_live_")
    assert key_record.key_prefix == raw_token[:12]
    # El token crudo no es igual al hash almacenado
    assert key_record.key_hash != raw_token


def test_verify_valid_api_key() -> None:
    session = _get_memory_session()
    user = create_user(session, email="bob@example.com", name="Bob Developer")
    _, raw_token = create_api_key(session, user_id=user.id)

    verified = verify_api_key(session, raw_token)
    assert verified is not None
    key_record, verified_user = verified
    assert verified_user.id == user.id
    assert verified_user.email == "bob@example.com"
    assert key_record.last_used_at is not None


def test_verify_invalid_api_key() -> None:
    session = _get_memory_session()
    assert verify_api_key(session, "invalid_token_123") is None
    assert verify_api_key(session, "wg_live_non_existent_key_00000000000000000000000000000") is None


def test_record_token_usage() -> None:
    session = _get_memory_session()
    user = create_user(session, email="charlie@example.com", name="Charlie")

    record_token_usage(session, user.id, tokens_used=1000, month="2026-08")
    usage1 = get_token_usage(session, user.id, month="2026-08")
    assert usage1 == 1000

    # Incrementar consumo
    record_token_usage(session, user.id, tokens_used=1500, month="2026-08")
    usage2 = get_token_usage(session, user.id, month="2026-08")
    assert usage2 == 2500


def test_save_pr_score() -> None:
    session = _get_memory_session()
    user = create_user(session, email="diana@example.com", name="Diana")

    layer_res = {
        "static": LayerResult(layer_name="static", risk_score=20, justification="ok"),
        "semantic": LayerResult(layer_name="semantic", risk_score=85, justification="suspicious"),
    }
    aggregated = AggregatedResult(
        score=47,
        semaforo=Semaforo.AMARILLO,
        layer_results=layer_res,
        weights_used={"static": 0.5, "semantic": 0.5},
        pr_id="42",
        repo="org/app",
        timestamp="2026-08-06T12:00:00Z",
    )

    pr_record = save_pr_score(session, aggregated_result=aggregated, user_id=user.id)
    assert pr_record.repo == "org/app"
    assert pr_record.pr_id == "42"
    assert pr_record.score == 47
    assert pr_record.semaforo == "amarillo"


def test_semantic_cache_operations() -> None:
    session = _get_memory_session()
    diff_hash_val = "abc123hash"

    assert get_semantic_cache(session, diff_hash_val) is None

    set_semantic_cache(session, diff_hash_val, '{"risk_score": 10}')
    cached_val = get_semantic_cache(session, diff_hash_val)
    assert cached_val == '{"risk_score": 10}'
