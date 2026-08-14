import os

import pytest


@pytest.fixture(autouse=True)
def set_env():
    os.environ['WATCHGATE_DB_SECRET'] = '1Vn6eB6nE7xO4yH0JkL4A-9tN1X5mK3bH2P8gV0zM8I='
    # Refresh fernet key
    from cryptography.fernet import Fernet

    import watchgate.db.crypto
    watchgate.db.crypto._fernet = Fernet('1Vn6eB6nE7xO4yH0JkL4A-9tN1X5mK3bH2P8gV0zM8I=')

from watchgate.db.crypto import decrypt_secret, encrypt_secret


def test_encrypt_decrypt_secret():
    plain = "ghp_myfaketoken123456"
    encrypted = encrypt_secret(plain)
    
    assert encrypted != plain
    assert decrypt_secret(encrypted) == plain

def test_encrypt_decrypt_none():
    assert encrypt_secret(None) is None
    assert decrypt_secret(None) is None
