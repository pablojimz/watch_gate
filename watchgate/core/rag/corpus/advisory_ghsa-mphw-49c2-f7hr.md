# Aviso: Malicious code in neutrl-core (PyPI) (GHSA-mphw-49c2-f7hr)

## Resumen

## Source: kam193 (f31badf901e75b93290ed22337225d71d1d3e97f2fb7aebd4fcffb4a1ad2bf0f)
This campaign exfiltrates sensitive environment variables, SSH keys, dotenv files and other credentials. The malicious code is hidden in a dependency package (e.g. neutrl-core) in a function disguised as telemetry, and requires activates once the attacker-controlled endpoint delivers the command. While the user can provide their blockchain endpoints, the code makes sure the malicious endpoint is always included in the configuration. In analyzed versions, the dependent packages did not use the malicious code but were clearly prepared for the supply chain attack. The related GitHub account faked the activity by publishing repositories with backdated commits (the account was created after any of the commits).


---

Category: MALICIOUS - The campaign has clearly malicious intent, like infostealers.


Campaign: 2026-08-neutrl-core


Reasons (based on the campaign):


 - files-exfiltration


 - exfiltration-env-variables


 - exfiltration-ssh-keys


 - crypto-related


 - action-hidden-in-lib-usage


 - The malicious code is intentionally included in a dependency of the package


 - exfiltration-crypto


 - The package contains code to execute remote commands (probably limited to a specific set) on the victim's machine.


 - exfiltration-credentials

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/dc8d4ed389b37ad42b1d9aa82974667f7cbab99b/osv/malicious/pypi/neutrl-core/MAL-2026-13710.json))

## Paquetes afectados

- `neutrl-core` (pip), versiones afectadas: = 2.0.0
- `neutrl-core` (pip), versiones afectadas: = 2.0.1
- `neutrl-core` (pip), versiones afectadas: = 2.0.2

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-10T21:31:57Z
- Fuente: https://github.com/advisories/GHSA-mphw-49c2-f7hr

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
