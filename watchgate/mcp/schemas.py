"""Esquemas Pydantic v2 para el servidor MCP y mensajes JSON-RPC 2.0 (watchgate/mcp/schemas.py)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class JsonRpcRequest(BaseModel):
    """Estructura de petición de mensaje JSON-RPC 2.0."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] | None = None


class JsonRpcResponse(BaseModel):
    """Estructura de respuesta de mensaje JSON-RPC 2.0."""

    jsonrpc: Literal["2.0"] = "2.0"
    id: int | str | None = None
    result: Any | None = None
    error: dict[str, Any] | None = None


class McpToolParameterSchema(BaseModel):
    """Esquema de propiedades JSON Schema para los parámetros de una herramienta MCP."""

    type: str = "object"
    properties: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class McpToolDefinition(BaseModel):
    """Definición de una herramienta en el servidor MCP."""

    name: str
    description: str
    inputSchema: McpToolParameterSchema


class McpTextContent(BaseModel):
    """Contenido de texto retornado por una herramienta MCP."""

    type: Literal["text"] = "text"
    text: str


class McpToolCallResult(BaseModel):
    """Resultado devuelto tras ejecutar una herramienta MCP."""

    content: list[McpTextContent] = Field(default_factory=list)
    isError: bool = False
