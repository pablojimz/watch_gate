"""Tests unitarios para el paquete unificado de persistencia (watchgate/db/)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlmodel import Session, create_engine

from watchgate.core.models import AggregatedResult, LayerResult, Semaforo
from watchgate.db.connection import SchemaOutOfDateError, init_db
from watchgate.db.models import User, UserAPIKey
from watchgate.db.repository import (
    create_api_key,
    create_user,
    get_repo_token_usage,
    get_semantic_cache,
    get_token_usage,
    record_repo_token_usage,
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


def test_init_db_fails_loudly_against_preexisting_db_missing_new_columns() -> None:
    """Caso real encontrado en revisión: `init_db()` solo hace `create_all()`,
    que no añade columnas a una tabla ya existente. Sin este chequeo, un
    despliegue contra una base de datos que ya tenía la tabla `users` de
    antes de la Fase 1 multi-tenant (sin `org_id`) fallaba mucho más tarde,
    con un `OperationalError: no such column: org_id` confuso dentro de
    `create_api_key`/`verify_api_key`. Ahora debe fallar aquí, en el
    arranque, con un mensaje explícito."""
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    # Tabla `users` mínima, "pre-Fase1": sin `org_id` (y sin el resto de
    # columnas nuevas), simulando una base de datos desplegada antes de
    # este cambio de esquema.
    with test_engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT NOT NULL, name TEXT NOT NULL)"
            )
        )
        conn.commit()

    with pytest.raises(SchemaOutOfDateError, match="users") as exc_info:
        init_db(test_engine)
    assert "org_id" in str(exc_info.value)


def test_create_user_and_api_key() -> None:
    session = _get_memory_session()
    user = create_user(
        session, email="alice@example.com", name="Alice Developer", role="mantenedor"
    )

    assert isinstance(user, User)
    assert user.email == "alice@example.com"
    assert user.role == "mantenedor"

    key_record, raw_token = create_api_key(
        session, user_id=user.id, name="Test Key", monitored_repo_id="test-repo-id"
    )

    assert isinstance(key_record, UserAPIKey)
    assert raw_token.startswith("wg_live_")
    assert key_record.key_prefix == raw_token[:12]
    # El token crudo no es igual al hash almacenado
    assert key_record.key_hash != raw_token


def test_verify_valid_api_key() -> None:
    session = _get_memory_session()
    user = create_user(session, email="bob@example.com", name="Bob Developer")
    _, raw_token = create_api_key(session, user_id=user.id, monitored_repo_id="test-repo-id")

    verified = verify_api_key(session, raw_token)
    assert verified is not None
    key_record, verified_user, _org = verified
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


def test_record_token_usage_atomic_under_concurrency(tmp_path) -> None:
    """Caso real encontrado en revisión, reproducido dos veces por separado:
    `record_token_usage` era un SELECT -> incrementar en Python -> UPDATE,
    no atómico. 20 hilos incrementando 100 tokens cada uno para el mismo
    user_id/mes perdían incrementos (de 2000 esperados, la BD terminaba con
    200-600) o lanzaban `IntegrityError` sin capturar. Ahora es un único
    `INSERT ... ON CONFLICT DO UPDATE` atómico -- no debe perder ninguno."""
    import threading

    db_path = tmp_path / "concurrency.db"
    test_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    init_db(test_engine)

    n_threads = 20
    tokens_per_call = 100
    errors: list[Exception] = []

    def worker() -> None:
        try:
            session = Session(test_engine)
            record_token_usage(
                session, user_id="agentA", tokens_used=tokens_per_call, month="2026-08"
            )
            session.close()
        except Exception as exc:  # noqa: BLE001 -- se recoge para el assert, no se traga
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    session = Session(test_engine)
    total = get_token_usage(session, user_id="agentA", month="2026-08")
    assert total == n_threads * tokens_per_call


def test_record_repo_token_usage() -> None:
    """Contraparte de `test_record_token_usage`, pero para `CostController`
    (modo CLI/engine local, cuota por repositorio, no por usuario)."""
    session = _get_memory_session()

    record_repo_token_usage(session, "acme/payments-api", tokens_used=500, month="2026-08")
    assert get_repo_token_usage(session, "acme/payments-api", month="2026-08") == 500

    record_repo_token_usage(session, "acme/payments-api", tokens_used=250, month="2026-08")
    assert get_repo_token_usage(session, "acme/payments-api", month="2026-08") == 750

    # Otro repo/mes no interfiere.
    assert get_repo_token_usage(session, "acme/other-repo", month="2026-08") == 0
    assert get_repo_token_usage(session, "acme/payments-api", month="2026-09") == 0


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

    # layer_results_json/weights_used_json deben ser JSON de verdad (no
    # str(dict) de Python, que usa comillas simples y True/False/None en vez
    # de true/false/null -- json.loads() sobre eso falla).
    import json

    parsed_layers = json.loads(pr_record.layer_results_json)
    assert parsed_layers["static"]["risk_score"] == 20
    parsed_weights = json.loads(pr_record.weights_used_json)
    assert parsed_weights == {"static": 0.5, "semantic": 0.5}


def test_semantic_cache_operations() -> None:
    session = _get_memory_session()
    diff_hash_val = "abc123hash"

    assert get_semantic_cache(session, diff_hash_val) is None

    set_semantic_cache(session, diff_hash_val, '{"risk_score": 10}')
    cached_val = get_semantic_cache(session, diff_hash_val)
    assert cached_val == '{"risk_score": 10}'
