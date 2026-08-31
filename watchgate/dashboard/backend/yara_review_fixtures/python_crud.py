"""Fragmento benigno de ejemplo: una función CRUD normal en Python."""

from __future__ import annotations

import sqlite3
from typing import Any


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> dict[str, Any] | None:
    cursor = conn.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "email": row[2]}


def update_user_email(conn: sqlite3.Connection, user_id: int, email: str) -> None:
    conn.execute("UPDATE users SET email = ? WHERE id = ?", (email, user_id))
    conn.commit()
