"""Inyección de dependencias para los routers de la Engine API."""

from __future__ import annotations

from watchgate.db.connection import get_db_session

__all__ = ["get_db_session"]
