"""Tests unitarios para Servidor MCP JSON-RPC 2.0 y herramientas (tests/unit/test_mcp_server.py)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from watchgate.core.models import (
    AggregatedResult,
    LayerResult,
    Semaforo,
)
from watchgate.mcp.server import handle_jsonrpc_request
from watchgate.mcp.tools import execute_mcp_tool, get_mcp_tools_list


def test_mcp_tools_list_schema() -> None:
    tools = get_mcp_tools_list()
    assert len(tools) == 8
    names = {t.name for t in tools}
    expected_names = {
        "watchgate_analyze_diff",
        "watchgate_precheck",
        "watchgate_explain_risk",
        "watchgate_verify_fix",
        "watchgate_query_threat_kb",
        "watchgate_repo_score_history",
        "watchgate_org_metrics",
        "watchgate_submit_feedback",
    }
    assert names == expected_names


def test_handle_jsonrpc_initialize() -> None:
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"},
    }
    resp = handle_jsonrpc_request(req)
    assert resp is not None
    assert resp.id == 1
    assert resp.error is None
    assert resp.result["serverInfo"]["name"] == "watchgate-mcp"


def test_handle_jsonrpc_ping() -> None:
    req = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
    resp = handle_jsonrpc_request(req)
    assert resp is not None
    assert resp.id == 2
    assert resp.result == {}


def test_handle_jsonrpc_tools_list() -> None:
    req = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}
    resp = handle_jsonrpc_request(req)
    assert resp is not None
    assert resp.id == 3
    tools = resp.result.get("tools", [])
    assert len(tools) == 8


def test_handle_jsonrpc_invalid_structure_and_method() -> None:
    # Structure not a dict
    resp = handle_jsonrpc_request("not a dict")  # type: ignore[arg-type]
    assert resp is not None
    assert resp.error["code"] == -32600

    # Unsupported method
    resp_method = handle_jsonrpc_request({"jsonrpc": "2.0", "id": 10, "method": "unknown/method"})
    assert resp_method is not None
    assert resp_method.error["code"] == -32601

    # Notification initialized returns None
    assert handle_jsonrpc_request({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_handle_jsonrpc_tool_call_internal_error() -> None:
    with patch("watchgate.mcp.server.execute_mcp_tool", side_effect=ValueError("Fallo interno")):
        req = {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {"name": "watchgate_precheck"},
        }
        resp = handle_jsonrpc_request(req)
        assert resp is not None
        assert resp.error["code"] == -32603
        assert "Fallo interno" in resp.error["message"]


def test_mcp_tool_precheck() -> None:
    diff_text = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
-print('old')
+print('new')
"""
    result = execute_mcp_tool("watchgate_precheck", {"diff_text": diff_text})
    assert not result.isError
    assert len(result.content) == 1
    data = json.loads(result.content[0].text)
    assert "analysis" in data
    assert "guidance" in data
    assert data["analysis"]["layer_results"]["semantic"]["skipped"] is True


def test_mcp_tool_analyze_diff() -> None:
    diff_text = """--- a/main.py
+++ b/main.py
@@ -0,0 +1,1 @@
+x = 1
"""
    result = execute_mcp_tool("watchgate_analyze_diff", {"diff_text": diff_text})
    assert not result.isError
    data = json.loads(result.content[0].text)
    assert "analysis" in data
    assert "guidance" in data


def test_mcp_tool_explain_risk() -> None:
    fake_aggregated = AggregatedResult(
        score=25,
        semaforo=Semaforo.VERDE,
        pr_id="123",
        repo="test/repo",
        timestamp="2026-08-10T12:00:00Z",
        weights_used={"static": 0.5, "semantic": 0.5},
        layer_results={
            "static": LayerResult(
                layer_name="static",
                risk_score=10,
                justification="Limpio",
            )
        },
    )
    result = execute_mcp_tool(
        "watchgate_explain_risk",
        {"analysis_json": fake_aggregated.model_dump_json()},
    )
    assert not result.isError
    explanation = result.content[0].text
    assert "Puntuación Global de Riesgo: 25/100" in explanation
    assert "VERDE" in explanation


def test_mcp_tool_verify_fix() -> None:
    orig_diff = """--- a/app.py
+++ b/app.py
@@ -0,0 +1,1 @@
+eval(input())
"""
    cand_diff = """--- a/app.py
+++ b/app.py
@@ -0,0 +1,1 @@
+print(input())
"""
    result = execute_mcp_tool(
        "watchgate_verify_fix",
        {"original_diff": orig_diff, "candidate_diff": cand_diff},
    )
    assert not result.isError
    data = json.loads(result.content[0].text)
    assert "risk_reduced" in data
    assert "previous_score" in data
    assert "new_score" in data


@patch("watchgate.mcp.tools.retrieve_relevant_context")
def test_mcp_tool_query_threat_kb(mock_retrieve: MagicMock) -> None:
    mock_retrieve.return_value = [
        MagicMock(
            case_name="xz_utils",
            origin="corpus",
            verdict="MALICIOUS",
            text="Compromiso de liblzma con backdoor.",
        )
    ]
    result = execute_mcp_tool("watchgate_query_threat_kb", {"query": "xz utils", "k": 1})
    assert not result.isError
    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["case_name"] == "xz_utils"


def test_handle_jsonrpc_tools_call() -> None:
    diff_text = "--- a/a.py\n+++ b/a.py\n@@ -0,0 +1,1 @@\n+pass\n"
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "watchgate_precheck",
            "arguments": {"diff_text": diff_text},
        },
    }
    resp = handle_jsonrpc_request(req)
    assert resp is not None
    assert resp.id == 4
    assert resp.result["isError"] is False
    content_text = resp.result["content"][0]["text"]
    assert "analysis" in content_text


# ---------------------------------------------------------------------------
# WATCHGATE_MCP_API_KEY -- identidad opcional para cuota y aislamiento del RAG
# ---------------------------------------------------------------------------


def _seed_org_user_and_key(session, *, org_quota: int = 100_000):
    from watchgate.db.repository import create_api_key, create_organization, create_user

    org = create_organization(session, name="Org MCP", monthly_token_quota=org_quota)
    user = create_user(
        session, email="mcp@example.com", name="MCP User", role="admin_organizacion", org_id=org.id
    )
    _api_key, raw_token = create_api_key(session, user_id=user.id, org_id=org.id)
    return org, user, raw_token


def test_resolve_mcp_identity_returns_none_without_env_var(monkeypatch) -> None:
    from watchgate.mcp.auth import resolve_mcp_identity

    monkeypatch.delenv("WATCHGATE_MCP_API_KEY", raising=False)
    session = MagicMock()
    assert resolve_mcp_identity(session) is None


def test_resolve_mcp_identity_returns_none_for_invalid_key(monkeypatch) -> None:
    from sqlmodel import Session, create_engine

    from watchgate.db.connection import init_db
    from watchgate.mcp.auth import resolve_mcp_identity

    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    init_db(test_engine)
    monkeypatch.setenv("WATCHGATE_MCP_API_KEY", "wg_live_no-existe-esta-key")
    with Session(test_engine) as session:
        assert resolve_mcp_identity(session) is None


def test_resolve_mcp_identity_returns_org_for_a_valid_key(monkeypatch, tmp_path) -> None:
    from sqlmodel import Session, create_engine

    from watchgate.db.connection import init_db
    from watchgate.mcp.auth import resolve_mcp_identity

    # Fichero real, no ":memory:" -- cada `Session(engine)` sobre un mismo
    # engine ":memory:" sin StaticPool ve una conexión (y por tanto una BD)
    # nueva y vacía; aquí solo hace falta una sesión, pero se usa el mismo
    # patrón que el resto de tests de este bloque por consistencia.
    test_engine = create_engine(f"sqlite:///{tmp_path / 'mcp.db'}")
    init_db(test_engine)
    with Session(test_engine) as session:
        org, user, raw_token = _seed_org_user_and_key(session)
        session.commit()
        expected_org_id = org.id
        expected_user_id = user.id

        monkeypatch.setenv("WATCHGATE_MCP_API_KEY", raw_token)
        identity = resolve_mcp_identity(session)

        # Comprobado dentro del `with`: tras `session.commit()`,
        # `expire_on_commit` (por defecto en SQLModel/SQLAlchemy) marca los
        # objetos ya cargados como expirados -- acceder a un atributo fuera
        # de la sesión (ya cerrada) lanza `DetachedInstanceError`.
        assert identity is not None
        api_key, resolved_user, resolved_org = identity
        assert resolved_org.id == expected_org_id
        assert resolved_user.id == expected_user_id
        assert api_key.org_id == expected_org_id


def test_analyze_diff_consumes_quota_when_mcp_api_key_is_configured(monkeypatch, tmp_path) -> None:
    """Hallazgo real de revisión: `watchgate_analyze_diff` llamaba a
    `run_full_analysis` directo, sin pasar nunca por `QuotaService` -- sin
    límite de presupuesto mensual y sin `org_id` que aislara el RAG. Con
    `WATCHGATE_MCP_API_KEY` configurada, ahora sí pasa por `QuotaService`
    (comprobado por su efecto observable más fiable: persiste un `PRScore`,
    algo que la llamada directa a `run_full_analysis` nunca hacía -- el
    `token_usage` neto puede quedar en 0 igualmente si no hay
    WATCHGATE_LLM_API_KEY en el entorno de test, porque la reserva se
    devuelve al reconciliar contra el consumo real cuando la capa semántica
    se omite por falta de proveedor LLM configurado)."""
    from sqlmodel import Session, create_engine, select

    from watchgate.db.connection import init_db
    from watchgate.db.models import PRScore

    test_engine = create_engine(f"sqlite:///{tmp_path / 'mcp.db'}")
    init_db(test_engine)
    with Session(test_engine) as session:
        org, _user, raw_token = _seed_org_user_and_key(session)
        session.commit()
        org_id = org.id

    monkeypatch.setenv("WATCHGATE_MCP_API_KEY", raw_token)
    monkeypatch.setattr("watchgate.mcp.auth.default_engine", test_engine)

    diff_text = "--- a/main.py\n+++ b/main.py\n@@ -0,0 +1,1 @@\n+x = 1\n"
    result = execute_mcp_tool("watchgate_analyze_diff", {"diff_text": diff_text})
    assert not result.isError

    with Session(test_engine) as session:
        scores = session.exec(select(PRScore).where(PRScore.org_id == org_id)).all()
    assert (
        len(scores) == 1
    )  # QuotaService.analyze_with_quota persiste PRScore; la llamada directa no


def test_analyze_diff_falls_back_to_direct_call_without_mcp_api_key(monkeypatch) -> None:
    """Sin `WATCHGATE_MCP_API_KEY`, el comportamiento sigue siendo el de
    siempre: análisis local directo, sin organización ni límites -- el caso
    de uso principal (un desarrollador solo) no debe requerir autenticarse."""
    monkeypatch.delenv("WATCHGATE_MCP_API_KEY", raising=False)
    diff_text = "--- a/main.py\n+++ b/main.py\n@@ -0,0 +1,1 @@\n+x = 1\n"
    result = execute_mcp_tool("watchgate_analyze_diff", {"diff_text": diff_text})
    assert not result.isError
    data = json.loads(result.content[0].text)
    assert "analysis" in data


@patch("watchgate.mcp.tools.retrieve_relevant_context")
def test_query_threat_kb_passes_org_id_when_mcp_api_key_is_configured(
    mock_retrieve: MagicMock, monkeypatch, tmp_path
) -> None:
    """Hallazgo real de revisión: sin `org_id`, la consulta al RAG distribuido
    no filtraba por organización -- el feedback humano de todas las
    organizaciones se veía mezclado. Con la key configurada, ahora se pasa
    el `org_id` real."""
    from sqlmodel import Session, create_engine

    from watchgate.db.connection import init_db

    # Fichero real, no ":memory:" -- ver nota en
    # test_resolve_mcp_identity_returns_org_for_a_valid_key.
    test_engine = create_engine(f"sqlite:///{tmp_path / 'mcp.db'}")
    init_db(test_engine)
    with Session(test_engine) as session:
        org, _user, raw_token = _seed_org_user_and_key(session)
        session.commit()
        org_id = org.id

    monkeypatch.setenv("WATCHGATE_MCP_API_KEY", raw_token)
    monkeypatch.setattr("watchgate.mcp.auth.default_engine", test_engine)
    mock_retrieve.return_value = []

    execute_mcp_tool("watchgate_query_threat_kb", {"query": "xz utils"})

    mock_retrieve.assert_called_once()
    assert mock_retrieve.call_args.kwargs["org_id"] == org_id


@patch("watchgate.mcp.tools.retrieve_relevant_context")
def test_query_threat_kb_passes_none_org_id_without_mcp_api_key(
    mock_retrieve: MagicMock, monkeypatch
) -> None:
    monkeypatch.delenv("WATCHGATE_MCP_API_KEY", raising=False)
    mock_retrieve.return_value = []

    execute_mcp_tool("watchgate_query_threat_kb", {"query": "xz utils"})

    mock_retrieve.assert_called_once()
    assert mock_retrieve.call_args.kwargs["org_id"] is None


# ---------------------------------------------------------------------------
# watchgate_repo_score_history / watchgate_org_metrics -- datos del Dashboard
# accesibles a agentes de IA vía MCP
# ---------------------------------------------------------------------------


def _configure_mcp_identity(monkeypatch, tmp_path):
    """Deja `WATCHGATE_MCP_API_KEY` configurada contra una org/usuario reales
    en una BD SQLModel de prueba, y devuelve `org_id` para las aserciones."""
    from sqlmodel import Session, create_engine

    from watchgate.db.connection import init_db

    test_engine = create_engine(f"sqlite:///{tmp_path / 'sqlmodel.db'}")
    init_db(test_engine)
    with Session(test_engine) as session:
        org, _user, raw_token = _seed_org_user_and_key(session)
        session.commit()
        org_id = org.id

    monkeypatch.setenv("WATCHGATE_MCP_API_KEY", raw_token)
    monkeypatch.setattr("watchgate.mcp.auth.default_engine", test_engine)
    return org_id


def _seed_dashboard_score(
    tmp_path, monkeypatch, *, repo: str, score: int, semaforo: str, user_login: str = "MCP User"
) -> None:
    from watchgate.core.models import AggregatedResult, LayerResult
    from watchgate.core.models import Semaforo as SemaforoEnum
    from watchgate.dashboard.backend import db as dashboard_db

    monkeypatch.setenv("WATCHGATE_DASHBOARD_DB", str(tmp_path / "dashboard.db"))
    monkeypatch.delenv("WATCHGATE_DASHBOARD_DATABASE_URL", raising=False)
    result = AggregatedResult(
        score=score,
        semaforo=SemaforoEnum(semaforo),
        pr_id="1",
        repo=repo,
        timestamp="2026-08-10T10:00:00Z",
        weights_used={"static": 1.0},
        layer_results={
            "static": LayerResult(layer_name="static", risk_score=score, justification="x")
        },
    )
    with dashboard_db.db_session() as conn:
        score_id = dashboard_db.insert_aggregated(conn, result, author_login="octocat")
        if user_login:
            dashboard_db.upsert_role(conn, user_login, repo, "revisor")
        return score_id


def test_repo_score_history_requires_mcp_api_key(monkeypatch) -> None:
    monkeypatch.delenv("WATCHGATE_MCP_API_KEY", raising=False)
    result = execute_mcp_tool("watchgate_repo_score_history", {"repo": "acme/webapp"})
    assert result.isError
    assert "WATCHGATE_MCP_API_KEY" in result.content[0].text


def test_mcp_repo_score_history_denied_without_role(monkeypatch, tmp_path) -> None:
    _configure_mcp_identity(monkeypatch, tmp_path)
    _seed_dashboard_score(
        tmp_path, monkeypatch, repo="acme/secret-repo", score=80, semaforo="rojo", user_login=""
    )

    result = execute_mcp_tool("watchgate_repo_score_history", {"repo": "acme/secret-repo"})
    assert result.isError
    assert "Permiso denegado" in result.content[0].text


def test_repo_score_history_returns_real_dashboard_data(monkeypatch, tmp_path) -> None:
    _configure_mcp_identity(monkeypatch, tmp_path)
    _seed_dashboard_score(tmp_path, monkeypatch, repo="acme/webapp", score=75, semaforo="rojo")

    result = execute_mcp_tool("watchgate_repo_score_history", {"repo": "acme/webapp"})
    assert not result.isError
    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["score"] == 75
    assert data[0]["semaforo"] == "rojo"
    assert data[0]["repo"] == "acme/webapp"


def test_repo_score_history_respects_limit(monkeypatch, tmp_path) -> None:
    _configure_mcp_identity(monkeypatch, tmp_path)
    for score in (10, 20, 30):
        _seed_dashboard_score(
            tmp_path, monkeypatch, repo="acme/webapp", score=score, semaforo="verde"
        )

    result = execute_mcp_tool("watchgate_repo_score_history", {"repo": "acme/webapp", "limit": 2})
    assert not result.isError
    data = json.loads(result.content[0].text)
    assert len(data) == 2


def test_org_metrics_requires_mcp_api_key(monkeypatch) -> None:
    monkeypatch.delenv("WATCHGATE_MCP_API_KEY", raising=False)
    result = execute_mcp_tool("watchgate_org_metrics", {})
    assert result.isError
    assert "WATCHGATE_MCP_API_KEY" in result.content[0].text


def test_org_metrics_aggregates_real_dashboard_data(monkeypatch, tmp_path) -> None:
    _configure_mcp_identity(monkeypatch, tmp_path)
    _seed_dashboard_score(tmp_path, monkeypatch, repo="acme/webapp", score=75, semaforo="rojo")
    _seed_dashboard_score(tmp_path, monkeypatch, repo="acme/otro", score=5, semaforo="verde")

    result = execute_mcp_tool("watchgate_org_metrics", {})
    assert not result.isError
    data = json.loads(result.content[0].text)
    assert data["total_prs"] == 2
    assert data["repos_count"] == 2


def test_org_metrics_scoped_to_explicit_repos_when_given(monkeypatch, tmp_path) -> None:
    _configure_mcp_identity(monkeypatch, tmp_path)
    _seed_dashboard_score(tmp_path, monkeypatch, repo="acme/webapp", score=75, semaforo="rojo")
    _seed_dashboard_score(tmp_path, monkeypatch, repo="acme/otro", score=5, semaforo="verde")

    result = execute_mcp_tool("watchgate_org_metrics", {"repos": ["acme/webapp"]})
    assert not result.isError
    data = json.loads(result.content[0].text)
    assert data["total_prs"] == 1


def test_mcp_tool_submit_feedback(monkeypatch, tmp_path) -> None:
    _configure_mcp_identity(monkeypatch, tmp_path)
    score_id = _seed_dashboard_score(
        tmp_path, monkeypatch, repo="acme/webapp", score=20, semaforo="verde"
    )

    result = execute_mcp_tool(
        "watchgate_submit_feedback", {"score_id": score_id, "feedback": "correcto"}
    )
    assert not result.isError
    data = json.loads(result.content[0].text)
    assert data["status"] == "success"
    assert data["score_id"] == score_id
    assert data["feedback"] == "correcto"
