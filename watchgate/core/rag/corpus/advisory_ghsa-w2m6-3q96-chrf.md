# Aviso: Malicious code in @opap/player-kyc-widget (npm) (GHSA-w2m6-3q96-chrf)

## Resumen

## Source: ossf-package-analysis (98e627cea85331a67652aa65927058579efe7046253a9ef22cb70b1d73916885)
The OpenSSF Package Analysis project identified '@opap/player-kyc-widget' @ 3.999.999 (npm) as malicious.

It is considered malicious because:

- The package communicates with a domain associated with malicious activity.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/194b5690d208d12c0c7f2c9034b1291010328e58/osv/malicious/npm/@opap/player-kyc-widget/MAL-2026-14387.json))

## Paquetes afectados

- `@opap/player-kyc-widget` (npm), versiones afectadas: = 3.999.999

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-23T21:31:02Z
- Fuente: https://github.com/advisories/GHSA-w2m6-3q96-chrf

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
