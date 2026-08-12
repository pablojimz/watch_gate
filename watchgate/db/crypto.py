"""Utilidades criptográficas para WatchGate.

Proporciona cifrado simétrico usando Fernet para secretos como tokens de acceso
o claves de API de terceros almacenados en la base de datos.
"""

from __future__ import annotations

import os
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import String, TypeDecorator

# Clave simétrica de 32 bytes (base64) para cifrar/descifrar secretos en DB.
# En producción debe inyectarse vía variable de entorno.
_SECRET_KEY = os.environ.get("WATCHGATE_DB_SECRET")

# Si no hay clave, no fallamos en el import, pero fallaremos si intentan cifrar.
_fernet: Fernet | None = None
if _SECRET_KEY:
    try:
        _fernet = Fernet(_SECRET_KEY.encode("utf-8"))
    except ValueError:
        pass


def _get_fernet() -> Fernet:
    if _fernet is None:
        raise RuntimeError(
            "WATCHGATE_DB_SECRET no está configurado o es inválido. "
            "Debe ser una clave generada por Fernet.generate_key() "
            "(32 url-safe base64-encoded bytes)."
        )
    return _fernet


def encrypt_secret(plain_text: str | None) -> str | None:
    """Cifra un texto plano en base64 usando Fernet."""
    if not plain_text:
        return plain_text
    f = _get_fernet()
    return f.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_secret(cipher_text: str | None) -> str | None:
    """Descifra un texto cifrado en base64 usando Fernet."""
    if not cipher_text:
        return cipher_text
    f = _get_fernet()
    return f.decrypt(cipher_text.encode("utf-8")).decode("utf-8")


class EncryptedString(TypeDecorator[str]):
    """Tipo personalizado de SQLAlchemy que cifra y descifra strings transparentemente."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        if value is not None:
            return encrypt_secret(value)
        return value

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        if value is not None:
            try:
                return decrypt_secret(value)
            except Exception:
                # Si falla el descifrado (ej. clave cambiada o datos sin cifrar previos),
                # devolvemos raw o None, pero idealmente loggeamos. Aquí por seguridad
                # devolvemos el valor original (asumiendo que pudo no estar cifrado
                # si se introdujo manualmente).
                return value
        return value
