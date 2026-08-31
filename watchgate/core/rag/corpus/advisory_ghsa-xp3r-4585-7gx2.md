# Aviso: Malicious code in octopus-action (npm) (GHSA-xp3r-4585-7gx2)

## Resumen

The package declares a preinstall lifecycle script (`node index.js`) that runs automatically on `npm install`. index.js collects the installer's hostname, OS username, home directory, configured DNS servers, package metadata, and the contents of /etc/passwd and /etc/hosts, then POSTs the payload over HTTPS to dfwvktnc563cparn1p88c8051w7ovej3.oastify.com, a Burp Collaborator out-of-band host controlled by a third party. Installing the package causes installer host identifiers and system files to be exfiltrated to that endpoint.

## Paquetes afectados

- `octopus-action` (npm), versiones afectadas: = 1.0.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-26T15:31:42Z
- Fuente: https://github.com/advisories/GHSA-xp3r-4585-7gx2

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre `octopus-action`, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
