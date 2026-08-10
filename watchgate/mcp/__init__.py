"""Paquete Servidor MCP (Model Context Protocol) para WatchGate (watchgate/mcp/)."""

from watchgate.mcp.server import run_stdio_server
from watchgate.mcp.tools import execute_mcp_tool, get_mcp_tools_list

__all__ = ["execute_mcp_tool", "get_mcp_tools_list", "run_stdio_server"]
