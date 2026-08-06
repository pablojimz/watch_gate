
import OpenSSL.SSL
from cryptography import x509

try:
    from cryptography.x509 import UnsupportedExtension  # type: ignore[attr-defined]
    return names


class WrappedSocket:
    """API-compatibility wrapper for Python OpenSSL's Connection-class."""

            return OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_ASN1, x509)

        return {
            "subject": ((("commonName", x509.get_subject().CN),),),  # type: ignore[dict-item]
            "subjectAltName": get_subj_alt_name(x509),
        }

        self,
        certfile: str,
        keyfile: str | None = None,
        password: str | None = None,
    ) -> None:
        try:
            self._ctx.use_certificate_chain_file(certfile)
            if password is not None:
                if not isinstance(password, bytes):
                    password = password.encode("utf-8")  # type: ignore[assignment]
                self._ctx.set_passwd_cb(lambda *_: password)  # type: ignore[arg-type]
            self._ctx.use_privatekey_file(keyfile or certfile)
        except OpenSSL.SSL.Error as e:
            raise ssl.SSLError(f"Unable to load certificate chain: {e!r}") from e

    def set_alpn_protocols(self, protocols: list[bytes | str]) -> None:
