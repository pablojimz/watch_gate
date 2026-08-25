# Aviso: Malicious code in multyproccess (PyPI) (GHSA-32gv-h6qj-hjm8)

## Resumen

## Source: kam193 (93a751dcfb2e5ac6058cbd62220d237288d3ceb4d8fe152b7ef7babb645df660)
During installation, package executes an infostealer that e.g. exfiltrates browsers and crypto wallets data, establishes persistence, monitors clipboard.


---

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.


Campaign: 2026-08-multyproccess


Reasons (based on the campaign):


 - typosquatting


 - infostealer


 - exfiltration-crypto


 - exfiltration-browser-data


 - clones-real-package


 - The package overrides the install command in setup.py to execute malicious code during installation.


 - The package contains code to detect if it is running in a sandbox environment.


 - obfuscation


 - persistence

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/c04e75e38121768f82fef0495de77b68b7054d7c/osv/malicious/pypi/multyproccess/MAL-2026-14401.json))

## Paquetes afectados

- `multyproccess` (pip), versiones afectadas: = 2.32.3
- `multyproccess` (pip), versiones afectadas: = 2.32.4
- `multyproccess` (pip), versiones afectadas: = 2.32.5
- `multyproccess` (pip), versiones afectadas: = 2.32.6

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-24T09:33:50Z
- Fuente: https://github.com/advisories/GHSA-32gv-h6qj-hjm8

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
