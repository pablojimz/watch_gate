"""Tests unitarios para QuotaService, PolicyService y Modo Degradado Inteligente."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime

from sqlmodel import Session, create_engine, select

import watchgate.service.quota as quota_module
from watchgate.config import WatchGateConfig
from watchgate.core.diffparser import parse_diff_from_text
from watchgate.core.models import AggregatedResult, LayerResult, Semaforo
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


def test_analyze_with_quota_overrides_client_supplied_org_id(monkeypatch) -> None:
    """Caso real encontrado en revisión: `metadata` llega de un payload HTTP
    sin validar (`AnalyzeRequest.metadata: dict[str, Any]`) y antes solo se
    inyectaba `org_id` si la clave no estaba ya presente -- un cliente
    autenticado como la Org A podía mandar `metadata={"org_id": "org-b"}` y
    la capa semántica filtraba el RAG distribuido por el feedback humano de
    la Org B (fuga cross-tenant), o vaciaba el filtro por completo con
    `org_id=None`/"" para ver el de TODAS las orgs mezclado. El `org_id`
    real -- el que resuelve la autenticación -- debe ganar siempre."""
    session = _get_memory_session()
    org_a = create_organization(session, name="Org A", monthly_token_quota=100_000)
    user = create_user(session, email="a@example.com", name="User A", org_id=org_a.id)

    captured_metadata: dict[str, object] = {}

    def _capturing_full_analysis(diff, metadata, config):  # noqa: ANN001, ARG001
        captured_metadata.update(metadata)
        return _fake_full_analysis(diff, metadata, config)

    monkeypatch.setattr(quota_module, "run_full_analysis", _capturing_full_analysis)

    diff = parse_diff_from_text(
        diff_text="--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-x = 1\n+x = 2",
        base_sha="0000000",
        head_sha="1111111",
    )
    quota_service = QuotaService(session)
    quota_service.analyze_with_quota(
        diff=diff,
        metadata={"pr_id": "1", "repo": "test/repo", "org_id": "org-b"},
        config=WatchGateConfig(),
        org_id=org_a.id,
        user_id=user.id,
    )

    assert captured_metadata["org_id"] == org_a.id


def _fake_full_analysis(diff, metadata, config):  # noqa: ANN001, ARG001
    """Doble rápido de `run_full_analysis`: simula una llamada real al LLM
    (con su latencia) sin red ni coste, para poder probar concurrencia."""
    time.sleep(0.05)
    return AggregatedResult(
        score=10,
        semaforo=Semaforo.VERDE,
        layer_results={
            "semantic": LayerResult(
                layer_name="semantic",
                risk_score=10,
                justification="ok",
                tool_calls_made=0,
            )
        },
        weights_used=config.weights,
        pr_id=str(metadata.get("pr_id", "")),
        repo=str(metadata.get("repo", "")),
        timestamp="2026-01-01T00:00:00Z",
    )


def test_analyze_with_quota_closes_toctou_window_under_concurrency(monkeypatch, tmp_path) -> None:
    """Caso real encontrado en revisión: la comprobación de cuota
    (`get_org_quota_status`) ocurría ANTES de la llamada al LLM (que tarda
    segundos) y el consumo se contabilizaba DESPUÉS -- peticiones
    concurrentes dentro de esa ventana leían todas "cuota no superada" y
    todas acababan llamando al LLM, permitiendo sobrepasar la cuota
    proporcionalmente a la concurrencia. Con una cuota de exactamente una
    "reserva" (3000 tokens) y 5 peticiones concurrentes, como mucho UNA
    puede completarse en modo estándar -- el resto debe degradarse, sin
    importar el orden de entrelazado de los hilos."""
    monkeypatch.setattr(quota_module, "run_full_analysis", _fake_full_analysis)

    # Fichero real en disco, no `:memory:` -- necesitamos una conexión
    # independiente y genuinamente concurrente por hilo (como en producción,
    # ver `connection.py::build_engine`); una única conexión compartida
    # (`StaticPool`) no soporta transacciones concurrentes de verdad y no
    # ejercitaría la condición de carrera real.
    db_path = tmp_path / "toctou.db"
    test_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    init_db(test_engine)

    session = Session(test_engine)
    org = create_organization(session, name="Race Org", monthly_token_quota=3000)
    user = create_user(session, email="race@example.com", name="Race User", org_id=org.id)
    session.commit()

    diff = parse_diff_from_text(
        diff_text="--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-x = 1\n+x = 2",
        base_sha="0000000",
        head_sha="1111111",
    )

    results: list[bool] = []
    lock = threading.Lock()

    def worker() -> None:
        thread_session = Session(test_engine)
        quota_service = QuotaService(thread_session)
        _result, is_degraded = quota_service.analyze_with_quota(
            diff=diff,
            metadata={"pr_id": "race", "repo": "test/race"},
            config=WatchGateConfig(),
            org_id=org.id,
            user_id=user.id,
        )
        with lock:
            results.append(is_degraded)
        thread_session.close()

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    n_standard = results.count(False)
    assert n_standard <= 1, (
        f"{n_standard} peticiones completaron en modo estándar con una cuota que solo "
        "debería permitir 1 -- la ventana TOCTOU no está cerrada."
    )
