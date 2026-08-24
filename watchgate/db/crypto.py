"""Utilidades criptográficas para WatchGate.

Proporciona cifrado simétrico usando Fernet para secretos como tokens de acceso
o claves de API de terceros almacenados en la base de datos.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import String, TypeDecorator

logger = logging.getLogger(__name__)

# Todo token Fernet serializa a base64url empezando por el byte de versión
# 0x80 -- "gAAAA..." como texto. Sirve para distinguir "esto ES un secreto
# cifrado que no se pudo descifrar" (clave rotada/ausente) de "esto es un
# valor legado guardado en claro antes de cifrar esta columna".
_FERNET_TOKEN_PREFIX = "gAAAA"

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
                if value.startswith(_FERNET_TOKEN_PREFIX):
                    # Es un secreto cifrado que no se puede descifrar (clave
                    # WATCHGATE_DB_SECRET rotada o ausente). Devolver el
                    # ciphertext crudo aquí -- lo que se hacía antes -- lo
                    # convertía en el "valor" del secreto para el resto del
                    # código, que lo usaba tal cual como token real en
                    # llamadas a APIs externas (fallo silencioso y opaco
                    # aguas abajo). None + warning hace el fallo visible en
                    # el punto donde ocurre.
                    logger.warning(
                        "No se pudo descifrar un secreto de la BD (¿WATCHGATE_DB_SECRET "
                        "rotada o ausente?). Se devuelve None en vez del ciphertext."
                    )
                    return None
                # Valor legado guardado en claro antes de que esta columna
                # se cifrara: se devuelve tal cual y quedará cifrado en la
                # siguiente escritura.
                return value
        return value
