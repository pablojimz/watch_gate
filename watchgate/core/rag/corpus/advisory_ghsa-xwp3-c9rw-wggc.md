# Aviso: Malicious code in company-sdk (PyPI) (GHSA-xwp3-c9rw-wggc)

## Resumen

company_sdk.py executes credential-harvesting code at module import time. It walks the installer's home directory reading SSH keys (~/.ssh), cloud credentials (~/.aws, ~/.azure, ~/.config/gcloud), package manager tokens (~/.npmrc, ~/.pypirc, ~/.netrc, ~/.pgpass), Docker/Kube configs,.env files, Vault/Terraform tokens, and shell history, and enumerates process environment variables whose names match credential keywords (TOKEN, SECRET, KEY, PASSWORD, AWS_, GITHUB_, etc.). The collected material is gzip-compressed, XOR-encrypted with a keystream derived via PBKDF2-HMAC-SHA256 from a hardcoded 32-byte hex passphrase, HMAC-tagged, and base64-encoded. The _drop() function then POSTs the encrypted blob to https://api.github.com/gists using a hardcoded ghp_-prefixed GitHub Personal Access Token as the Bearer credential, with TLS verification explicitly disabled (ssl.CERT_NONE). The upload runs unconditionally on import inside a bare try/except so failures are silent. Using GitHub Gist as the drop channel routes the exfiltration through a domain that typically bypasses egress filtering, and encrypting the payload with an author-only key conceals contents from network inspection.

During import, package exfiltrates sensitive files, credentials and env variables to a private GitHub Gist.

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.

Campaign: 2026-09-company-sdk

Reasons (based on the campaign):

 - exfiltration-env-variables

 - files-exfiltration

 - exfiltration-credentials

 - exfiltration-ssh-keys

## Paquetes afectados

- `company-sdk` (pip), versiones afectadas: = 0.0.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-09-03T03:31:17Z
- Fuente: https://github.com/advisories/GHSA-xwp3-c9rw-wggc

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `company-sdk`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
