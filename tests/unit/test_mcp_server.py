"""Tests unitarios para el Servidor MCP JSON-RPC 2.0 y sus 5 herramientas (tests/unit/test_mcp_server.py)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from watchgate.core.models import (
    AggregatedResult,
    LayerResult,
    Semaforo,
    ThreatNature,
)
from watchgate.mcp.schemas import JsonRpcRequest
from watchgate.mcp.server import handle_jsonrpc_request
from watchgate.mcp.tools import execute_mcp_tool, get_mcp_tools_list


def test_mcp_tools_list_schema() -> None:
    tools = get_mcp_tools_list()
    assert len(tools) == 5
    names = {t.name for t in tools}
    expected_names = {
        "watchgate_analyze_diff",
        "watchgate_precheck",
        "watchgate_explain_risk",
        "watchgate_verify_fix",
        "watchgate_query_threat_kb",
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
    assert len(tools) == 5


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
    result = execute_mcp_tool(
        "watchgate_query_threat_kb", {"query": "xz utils", "k": 1}
    )
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
