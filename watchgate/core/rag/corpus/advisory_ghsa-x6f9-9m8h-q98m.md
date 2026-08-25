# Aviso: Malicious code in joule-btp-extension (PyPI) (GHSA-x6f9-9m8h-q98m)

## Resumen

## Source: kam193 (21a7a58b1f32893cafb7cd9a1b452c5e9138b8fa89c43ebef1b3722205f60596)
During installation, the code exfiltrates basic information and exfiltrates more information to a localhost service as well as starts a reverse shell there. It seems to be an internal test that was uploaded to a public repository.


---

Category: PROBABLY_PENTEST - Packages looking like typical pentest packages, but also anything that looks like testing, exploring pre-prepared kits, research & co, with clearly low-harm possibilities.


Campaign: 2026-08-joule-btp-extension


Reasons (based on the campaign):


 - The package contains code to create a reverse shell, allowing an attacker to execute any commands on the victim's machine.


 - The package contains code to exfiltrate basic data from the system, like IP or username. It has a limited risk.

## Source: ossf-package-analysis (65193272cd9bd3b918d955bb215650b6b89b171e458b3385819f989bc1128049)
The OpenSSF Package Analysis project identified 'joule-btp-extension' @ 0.1.6 (pypi) as malicious.

It is considered malicious because:

- The package communicates with a domain associated with malicious activity.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/a45f663d9dabf0ad2877d1c31d8cc1f30744b49c/osv/malicious/pypi/joule-btp-extension/MAL-2026-13732.json))

## Paquetes afectados

- `joule-btp-extension` (pip), versiones afectadas: = 0.1.6
- `joule-btp-extension` (pip), versiones afectadas: = 0.1.0
- `joule-btp-extension` (pip), versiones afectadas: = 0.1.1
- `joule-btp-extension` (pip), versiones afectadas: = 0.1.3
- `joule-btp-extension` (pip), versiones afectadas: = 0.1.4

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-11T12:30:29Z
- Fuente: https://github.com/advisories/GHSA-x6f9-9m8h-q98m

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
