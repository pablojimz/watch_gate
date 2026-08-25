# Aviso: Malicious code in sm-checkout (npm) (GHSA-pxgj-j29f-m7fq)

## Resumen

## Source: amazon-inspector (0bc8dabb0ecf46dc57dd07dacdf28c9cddf629ffb8e9b0cea75e71cd999feaf0)
sm-checkout@99.0.0 declares preinstall and postinstall lifecycle scripts in package.json that invoke curl against a hardcoded bare-IP URL over plain HTTP (http://16.192.173.5/sm-checkout/pre and http://16.192.173.5/sm-checkout/post) on npm install. The inflated 99.0.0 version is calibrated to win semver resolution against a private package of the same name, and the lifecycle callbacks confirm successful execution on any host that mistakenly resolves the public name, leaking the installer's source IP and install timing to the operator of 16.192.173.5. A source comment self-labels the package as a dependency-confusion test; the labelling does not change that the artifact runs an unauthenticated outbound beacon on every install in build systems and developer machines that pull it.

## Source: ossf-package-analysis (7e0e304166bd31c7677998bce3b0fa29ce87fcf40861c714a8f69417fc1083d1)
The OpenSSF Package Analysis project identified 'sm-checkout' @ 99.0.1 (npm) as malicious.

It is considered malicious because:

- The package executes one or more commands associated with malicious behavior.

---

Credit: [OpenSSF](https://github.com/ossf/malicious-packages) ([source](https://github.com/ossf/malicious-packages/blob/69cf85db3ebafc0534169441a15154ec56e73b2b/osv/malicious/npm/sm-checkout/MAL-2026-14397.json))

## Paquetes afectados

- `sm-checkout` (npm), versiones afectadas: = 99.0.0
- `sm-checkout` (npm), versiones afectadas: = 99.0.1

## Datos del aviso

- Tipo de aviso: malware
- Severidad: critical
- Publicado: 2026-08-24T06:30:33Z
- Fuente: https://github.com/advisories/GHSA-pxgj-j29f-m7fq

## Patrón a vigilar

Diff que añade (o fija por primera vez) una dependencia sobre cualquiera de los paquetes listados arriba, en cualquier versión del rango afectado -- el paquete en sí ES el malware, no hace falta ningún otro cambio sospechoso en el diff para que el riesgo sea máximo.
