# Aviso: Malicious code in envprovision (PyPI) (GHSA-xr9j-7gjp-x8fg)

## Resumen

## Source: kam193 (cf3a48b407852ec03ead22bb8c16c03f252ba5fafa5c86ed1a739427e7d7d869)
Exported functions hide the malicious functionality. On Windows, it downloads and installs a malicious executable, and disguises it as a system utility. After installation, the code attempts to cover its tracks by cleaning logs and removing downloaded files. The installed executable is a heavily obfuscated malware with multiple sandbox evasion techniques, finally running an infostealer identifying itself as "Snow Stealer". It collects at least browser data and modifies cryptowallet applications.


---

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.


Campaign: 2026-08-envprovision


Reasons (based on the campaign):


 - Downloads and executes a remote executable.


 - action-hidden-in-lib-usage


 - covering-tracks


 - persistence


 - The package contains code to detect if it is running in a sandbox environment.


 - obfuscation


 - malware


 - infostealer


 - exfiltration-browser-data


 - exfiltration-crypto

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/9b8482f28baf0740d7397ce1b610587289a34c80/osv/malicious/pypi/envprovision/MAL-2026-14389.json))

## Paquetes afectados

- `envprovision` (pip), versiones afectadas: = 1.2.0
- `envprovision` (pip), versiones afectadas: = 1.3.0
- `envprovision` (pip), versiones afectadas: = 1.4.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-24T00:33:13Z
- Fuente: https://github.com/advisories/GHSA-xr9j-7gjp-x8fg

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
