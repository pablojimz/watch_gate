
import OpenSSL.SSL
from cryptography import x509
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509.oid import NameOID

try:
    from cryptography.x509 import UnsupportedExtension  # type: ignore[attr-defined]
    return names


def _get_common_name(peer_cert: X509) -> str | None:
    """
    Given a pyOpenSSL certificate, return the subject's common name.
    """
    cert = peer_cert.to_cryptography()
    names = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    return typing.cast(str, names[0].value) if names else None


class WrappedSocket:
    """API-compatibility wrapper for Python OpenSSL's Connection-class."""

            return OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_ASN1, x509)

        return {
            "subject": ((("commonName", _get_common_name(x509)),),),  # type: ignore[dict-item]
            "subjectAltName": get_subj_alt_name(x509),
        }

        self,
        certfile: str,
        keyfile: str | None = None,
        password: str | bytes | None = None,
    ) -> None:
        try:
            self._ctx.use_certificate_chain_file(certfile)
            if password is not None:
                if not isinstance(password, bytes):
                    password = password.encode("utf-8")
                # pyOpenSSL added cryptography-key support in 24.3.0.
                # Keep using the older password-callback path until 2026's
                # versions because set_passwd_cb() became deprecated in 26.3.0.
                if int(OpenSSL.__version__.split(".")[0]) >= 26:
                    with open(keyfile or certfile, "rb") as key_file:
                        private_key = load_pem_private_key(key_file.read(), password)
                    # cryptography's loader returns a wider private-key union
                    # than pyOpenSSL accepts, so we add `type: ignore` here.
                    self._ctx.use_privatekey(private_key)  # type: ignore[arg-type]
                else:
                    self._ctx.set_passwd_cb(lambda *_: password)
                    self._ctx.use_privatekey_file(keyfile or certfile)
            else:
                self._ctx.use_privatekey_file(keyfile or certfile)
        except (OpenSSL.SSL.Error, TypeError, ValueError) as e:
            raise ssl.SSLError(f"Unable to load certificate chain: {e!r}") from e

    def set_alpn_protocols(self, protocols: list[bytes | str]) -> None:
