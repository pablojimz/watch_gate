# Aviso: Malicious code in libasync (PyPI) (GHSA-7vpc-7xx6-5v47)

## Resumen

## Source: kam193 (a46929f4ba4ca97beaf5511f0be0af36c4d1e9deff65bea3821137c2c258eb9c)
During import, the code obfuscated in native extension downloads malicious remote executable and establishes persistence via registry keys. Downloaded binary seems to be used for cryptomining.

 Attacker infrastructure corresponds with the campaign 2026-07-pyqt6darktheme.


---

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.


Campaign: 2026-08-libasync


Reasons (based on the campaign):


 - Downloads and executes a remote executable.


 - obfuscation


 - The package contains code to detect if it is running in a sandbox environment.


 - native-extension


 - persistence


 - cryptominer

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/d218bd7451cf256c2509cd7bab68bf0b4031c433/osv/malicious/pypi/libasync/MAL-2026-14308.json))

## Paquetes afectados

- `libasync` (pip), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-20T00:35:10Z
- Fuente: https://github.com/advisories/GHSA-7vpc-7xx6-5v47

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
