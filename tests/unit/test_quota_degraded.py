"""Tests unitarios para QuotaService, PolicyService y Modo Degradado Inteligente."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlmodel import Session, create_engine, select

from watchgate.config import WatchGateConfig
from watchgate.core.diffparser import parse_diff_from_text
from watchgate.db.connection import init_db
from watchgate.db.models import PRScore
from watchgate.db.repository import (
    create_api_key,
    create_organization,
    create_user,
    get_token_usage,
    record_token_usage,
)
from watchgate.service.policy import PolicyService
from watchgate.service.quota import QuotaService


def _get_memory_session() -> Session:
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    init_db(test_engine)
    return Session(test_engine)


def test_policy_service_overrides() -> None:
    session = _get_memory_session()
    base_config = WatchGateConfig()

    # Org sin policy_json
    org_no_policy = create_organization(session, name="Org No Policy")
    cfg1 = PolicyService.apply_policy_overrides(base_config, org_no_policy)
    assert cfg1.weights == base_config.weights

    # Org con policy_json
    policy_data = {
        "weights": {
            "static": 0.4,
            "dependencies": 0.4,
            "vulnerabilities": 0.1,
            "reputation": 0.1,
            "semantic": 0.0,
        },
        "thresholds": {"yellow": 30, "red": 60},
        "block_on_red": False,
        "shortcircuit_enabled": True,
    }
    org_policy = create_organization(
        session, name="Org Policy", policy_json=json.dumps(policy_data)
    )

    cfg2 = PolicyService.apply_policy_overrides(base_config, org_policy)
    assert cfg2.thresholds["red"] == 60
    assert cfg2.thresholds["yellow"] == 30
    assert cfg2.block_on_red is False
    assert cfg2.shortcircuit_enabled is True
    assert cfg2.weights["static"] == 0.4


def test_quota_service_standard_mode() -> None:
    session = _get_memory_session()
    org = create_organization(session, name="Standard Org", monthly_token_quota=100_000)
    user = create_user(session, email="std@example.com", name="Standard User", org_id=org.id)
    key_rec, _ = create_api_key(session, user_id=user.id, org_id=org.id)

    diff = parse_diff_from_text(
        diff_text="--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-print('hello')\n+print('world')",
        base_sha="0000000",
        head_sha="1111111",
    )

    quota_service = QuotaService(session)

    # Verificar estado de cuota
    is_exceeded, used, quota = quota_service.get_org_quota_status(org.id)
    assert is_exceeded is False
    assert used == 0
    assert quota == 100_000

    config = WatchGateConfig()
    result, is_degraded = quota_service.analyze_with_quota(
        diff=diff,
        metadata={"pr_id": "1", "repo": "test/repo"},
        config=config,
        org_id=org.id,
        user_id=user.id,
        agent_id=key_rec.default_agent_name,
    )

    assert is_degraded is False
    assert result.score >= 0

    # Verificar que se guardó en PRScore
    stmt = select(PRScore).where(PRScore.org_id == org.id)
    score_rec = session.exec(stmt).first()
    assert score_rec is not None
    assert score_rec.pr_id == "1"


def test_quota_service_degraded_mode() -> None:
    session = _get_memory_session()
    # Crear organización con cuota baja de 1,000 tokens
    org = create_organization(session, name="Low Quota Org", monthly_token_quota=1000)
    user = create_user(session, email="low@example.com", name="Low Quota User", org_id=org.id)

    current_month = datetime.now(UTC).strftime("%Y-%m")
    # Consumir previamente 1,500 tokens (superando el límite de 1,000)
    record_token_usage(
        session, user_id=user.id, tokens_used=1500, month=current_month, org_id=org.id
    )

    quota_service = QuotaService(session)
    is_exceeded, used, quota = quota_service.get_org_quota_status(org.id)
    assert is_exceeded is True
    assert used == 1500

    diff = parse_diff_from_text(
        diff_text="--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-x = 1\n+x = 2",
        base_sha="0000000",
        head_sha="1111111",
    )

    config = WatchGateConfig()
    result, is_degraded = quota_service.analyze_with_quota(
        diff=diff,
        metadata={"pr_id": "99", "repo": "test/degraded"},
        config=config,
        org_id=org.id,
        user_id=user.id,
    )

    # Verificar activación del Modo Degradado Inteligente
    assert is_degraded is True
    assert result.score >= 0

    # Verificar que la capa semántica fue omitida con el skip_reason explícito
    sem_layer = result.layer_results.get("semantic")
    assert sem_layer is not None
    assert sem_layer.skipped is True
    assert "Cuota mensual de tokens alcanzada" in (sem_layer.skip_reason or "")

    # Verificar que no se sumaron tokens adicionales durante la ejecución degradada
    current_usage = get_token_usage(session, month=current_month, org_id=org.id)
    assert current_usage == 1500
