"""Resolución opcional de identidad de organización para el servidor MCP.

El servidor MCP (`server.py`) es un proceso local por diseño -- un agente de
IDE (Cursor, Claude Code, VS Code...) lo lanza como subproceso y le habla por
stdio, sin ningún concepto de sesión HTTP ni API Key por defecto. Eso deja un
hueco real encontrado en revisión: las tools de análisis (`watchgate_analyze_
diff`, `watchgate_verify_fix`) llamaban a `run_full_analysis()` directamente,
sin pasar por `QuotaService` -- ningún límite de presupuesto mensual, ningún
registro de coste, y sin `org_id` que propagar al RAG distribuido (la misma
fuga cross-tenant que ya se cerró para la API REST de agentes, aquí sin
cerrar). `watchgate_query_threat_kb` tampoco filtraba el feedback humano por
organización.

En vez de exigir autenticación siempre (rompería el caso de uso principal --
un desarrollador solo, con su propia clave de LLM, sin organización ninguna
que gestionar), la identidad es *opcional*: si `WATCHGATE_MCP_API_KEY` está
configurada y es válida, las tools de análisis pasan por `QuotaService` (con
cuota, coste registrado y `org_id` propagado al RAG) exactamente igual que la
API REST de agentes -- misma clave, mismo mecanismo de verificación
(`verify_api_key`), ninguna ruta de autenticación nueva que mantener. Sin
ella, el comportamiento es el de siempre: análisis local, sin límites, sin
organización.
"""

from __future__ import annotations

import os

from sqlmodel import Session

from watchgate.db.connection import default_engine
from watchgate.db.models import Organization, User, UserAPIKey
from watchgate.db.repository import verify_api_key

_MCP_API_KEY_ENV_VAR = "WATCHGATE_MCP_API_KEY"


def resolve_mcp_identity(session: Session) -> tuple[UserAPIKey, User, Organization] | None:
    """`None` si `WATCHGATE_MCP_API_KEY` no está configurada, no es una API
    Key válida, o no tiene una organización asociada -- las tools que la
    llaman deben tratar `None` como "sin contexto de organización", no como
    un error: es el modo de uso local sin autenticar, válido por diseño."""
    token = os.environ.get(_MCP_API_KEY_ENV_VAR)
    if not token:
        return None
    verified = verify_api_key(session, token)
    if verified is None:
        return None
    api_key, user, org = verified
    if org is None:
        return None
    return api_key, user, org


def open_session() -> Session:
    """Una sesión de BD nueva por invocación de tool -- mismo patrón que
    `watchgate.db.connection.get_db_session` (generador de FastAPI), pero
    usable fuera de un contexto de request HTTP."""
    return Session(default_engine)
