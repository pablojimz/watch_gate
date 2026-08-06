import posixpath
import secrets

DEFAULT_PBKDF2_ITERATIONS = 1_000_000

_os_alt_seps: list[str] = list(
}


def _hash_internal(method: str, salt: str, password: str) -> tuple[str, str]:
    method, *args = method.split(":")
    salt_bytes = salt.encode()
    .. versionchanged:: 2.3
        The default iterations for pbkdf2 was increased to 600,000.
    """
    if salt_length <= 0:
        raise ValueError("Salt length must be at least 1.")

    salt = secrets.token_urlsafe(salt_length)
    h, actual_method = _hash_internal(method, salt, password)
    return f"{actual_method}${salt}${h}"

