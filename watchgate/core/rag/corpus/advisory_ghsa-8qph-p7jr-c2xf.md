# Aviso: Malicious code in fund-portfolio (npm) (GHSA-8qph-p7jr-c2xf)

## Resumen

## Source: ossf-package-analysis (ffad2f6c37441c2924e67b1d506d9c26dc9cb2fae325b74a596102ea5ed403bf)
The OpenSSF Package Analysis project identified 'fund-portfolio' @ 999.9.12 (npm) as malicious.

It is considered malicious because:

- The package communicates with a domain associated with malicious activity.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/9ad5c01dd991de677a31a824e81abae1e899f1ad/osv/malicious/npm/fund-portfolio/MAL-2026-14381.json))

## Paquetes afectados

- `fund-portfolio` (npm), versiones afectadas: = 999.9.12

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-23T12:31:07Z
- Fuente: https://github.com/advisories/GHSA-8qph-p7jr-c2xf

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
