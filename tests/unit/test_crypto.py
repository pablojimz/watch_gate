import os

import pytest


@pytest.fixture(autouse=True)
def set_env():
    os.environ["WATCHGATE_DB_SECRET"] = "1Vn6eB6nE7xO4yH0JkL4A-9tN1X5mK3bH2P8gV0zM8I="
    # Refresh fernet key
    from cryptography.fernet import Fernet

    import watchgate.db.crypto

    watchgate.db.crypto._fernet = Fernet("1Vn6eB6nE7xO4yH0JkL4A-9tN1X5mK3bH2P8gV0zM8I=")


from watchgate.db.crypto import EncryptedString, decrypt_secret, encrypt_secret  # noqa: E402


def test_encrypt_decrypt_secret():
    plain = "ghp_myfaketoken123456"
    encrypted = encrypt_secret(plain)

    assert encrypted != plain
    assert decrypt_secret(encrypted) == plain


def test_encrypt_decrypt_none():
    assert encrypt_secret(None) is None
    assert decrypt_secret(None) is None


def test_undecryptable_fernet_token_reads_as_none_not_ciphertext():
    """Regresión: si la clave rota (el valor cifrado ya no descifra), antes
    se devolvía el CIPHERTEXT crudo como si fuera el secreto -- y el resto
    del código lo usaba tal cual como token en llamadas a APIs externas.
    Ahora un valor que ES un token Fernet pero no descifra lee como None."""
    from cryptography.fernet import Fernet

    other_key_token = Fernet(Fernet.generate_key()).encrypt(b"secreto").decode("utf-8")
    assert other_key_token.startswith("gAAAA")

    result = EncryptedString().process_result_value(other_key_token, dialect=None)
    assert result is None


def test_legacy_plaintext_value_is_returned_as_is():
    """Un valor guardado en claro ANTES de que su columna se cifrara (p. ej.
    llm_settings.api_key) no parece un token Fernet: debe devolverse tal
    cual (y se re-cifrará en la siguiente escritura), no perderse."""
    result = EncryptedString().process_result_value("sk-ant-legacy-plaintext", dialect=None)
    assert result == "sk-ant-legacy-plaintext"
