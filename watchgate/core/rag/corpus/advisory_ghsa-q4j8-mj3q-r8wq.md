# Aviso: Malicious code in hyperion-react-native-testapp (npm) (GHSA-q4j8-mj3q-r8wq)

## Resumen

The package communicates with a domain associated with malicious activity.## Source: amazon-inspector (09dade0de8238a15a0ae8541c47a5178f3234eb654cc6afe58eaf02600ad4d47)
package.json declares a preinstall lifecycle script that runs `wget` at npm install time, sending the installer's username ($(whoami)), current working directory ($(pwd)), and hostname ($(hostname)) as URL query parameters to a hardcoded webhook.site collector (https://webhook.site/c4919b2f-dd76-4a2f-adca-2f052bc8ff0e/). This fires unconditionally on `npm install` without user consent and delivers installer identity/environment data to a third-party collector controlled by whoever created the webhook. The package name pattern and beacon shape are consistent with a dependency-confusion proof-of-concept, but the exfiltration behavior is real regardless of intent.

## Paquetes afectados

- `hyperion-react-native-testapp` (npm), versiones afectadas: = 1.0.0

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-25T09:30:43Z
- Fuente: https://github.com/advisories/GHSA-q4j8-mj3q-r8wq

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `hyperion-react-native-testapp`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
