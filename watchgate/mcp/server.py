"""Servidor MCP JSON-RPC 2.0 nativo sobre stdio (watchgate/mcp/server.py)."""

from __future__ import annotations

import json
import sys
from typing import Any

from watchgate.mcp.schemas import JsonRpcRequest, JsonRpcResponse
from watchgate.mcp.tools import execute_mcp_tool, get_mcp_tools_list


def _send_response(response: JsonRpcResponse) -> None:
    """Envía una respuesta JSON-RPC a stdout asegurando el ilado de líneas."""
    raw_json = json.dumps(response.model_dump(exclude_none=True))
    sys.stdout.write(raw_json + "\n")
    sys.stdout.flush()


def handle_jsonrpc_request(request_dict: dict[str, Any]) -> JsonRpcResponse | None:
    """Procesa una petición JSON-RPC 2.0 devolviendo la respuesta (o None si es notificación)."""
    if not isinstance(request_dict, dict):
        return JsonRpcResponse(
            id=None,
            error={"code": -32600, "message": "Estructura de petición JSON-RPC inválida."},
        )

    try:
        req = JsonRpcRequest.model_validate(request_dict)
    except Exception as exc:
        return JsonRpcResponse(
            id=request_dict.get("id") if isinstance(request_dict, dict) else None,
            error={"code": -32600, "message": f"Petición JSON-RPC inválida: {exc}"},
        )

    method = req.method
    req_id = req.id
    params = req.params or {}

    # Las notificaciones no requieren respuesta
    is_notification = req_id is None

    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
            },
            "serverInfo": {
                "name": "watchgate-mcp",
                "version": "0.1.0",
            },
        }
        return JsonRpcResponse(id=req_id, result=result)

    elif method == "notifications/initialized":
        return None

    elif method == "ping":
        return JsonRpcResponse(id=req_id, result={})

    elif method == "tools/list":
        tools = get_mcp_tools_list()
        tools_data = [t.model_dump() for t in tools]
        return JsonRpcResponse(id=req_id, result={"tools": tools_data})

    elif method == "tools/call":
        tool_name = str(params.get("name", ""))
        arguments = params.get("arguments") or {}
        try:
            tool_result = execute_mcp_tool(tool_name, arguments)
            return JsonRpcResponse(id=req_id, result=tool_result.model_dump())
        except Exception as exc:
            return JsonRpcResponse(
                id=req_id,
                error={
                    "code": -32603,
                    "message": f"Error interno ejecutando herramienta '{tool_name}': {exc}",
                },
            )

    else:
        if is_notification:
            return None
        return JsonRpcResponse(
            id=req_id,
            error={"code": -32601, "message": f"Método no soportado: '{method}'"},
        )


def run_stdio_server() -> int:
    """Bucle principal del servidor MCP leyendo mensajes de stdin y respondiendo en stdout."""
    sys.stderr.write("Iniciando Servidor MCP WatchGate en modo stdio...\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line_str = line.strip()
        if not line_str:
            continue

        try:
            request_dict = json.loads(line_str)
        except json.JSONDecodeError as err:
            err_resp = JsonRpcResponse(
                id=None,
                error={"code": -32700, "message": f"Error de parseo JSON: {err}"},
            )
            _send_response(err_resp)
            continue

        response = handle_jsonrpc_request(request_dict)
        if response is not None:
            _send_response(response)

    return 0
