# Aviso: Malicious code in fund-list-filter (npm) (GHSA-ww7v-m7hw-7m2q)

## Resumen

## Source: ossf-package-analysis (d7cde5bd15beab8488f3b3b6bde2f17fff6c148ef2d575613762f337bd1c8281)
The OpenSSF Package Analysis project identified 'fund-list-filter' @ 999.9.12 (npm) as malicious.

It is considered malicious because:

- The package communicates with a domain associated with malicious activity.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/9ad5c01dd991de677a31a824e81abae1e899f1ad/osv/malicious/npm/fund-list-filter/MAL-2026-14380.json))

## Paquetes afectados

- `fund-list-filter` (npm), versiones afectadas: = 999.9.12

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-23T12:31:07Z
- Fuente: https://github.com/advisories/GHSA-ww7v-m7hw-7m2q

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
