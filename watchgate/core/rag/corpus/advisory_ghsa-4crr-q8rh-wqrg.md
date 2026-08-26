# Aviso: Malicious code in plp-contract (PyPI) (GHSA-4crr-q8rh-wqrg)

## Resumen

This package intentionally depends on a malicious package.

This campaign exfiltrates sensitive environment variables, SSH keys, dotenv files and other credentials. The malicious code is hidden in a dependency package (e.g. neutrl-core) in a function disguised as telemetry, and requires activates once the attacker-controlled endpoint delivers the command. While the user can provide their blockchain endpoints, the code makes sure the malicious endpoint is always included in the configuration. In analyzed versions, the dependent packages did not use the malicious code but were clearly prepared for the supply chain attack. The related GitHub account faked the activity by publishing repositories with backdated commits (the account was created after any of the commits).

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

## Paquetes afectados

- `plp-contract` (pip), versiones afectadas: = 2.0.0
- `plp-contract` (pip), versiones afectadas: = 2.0.1
- `plp-contract` (pip), versiones afectadas: = 2.0.2

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-10T21:31:57Z
- Fuente: https://github.com/advisories/GHSA-4crr-q8rh-wqrg

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `plp-contract`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
