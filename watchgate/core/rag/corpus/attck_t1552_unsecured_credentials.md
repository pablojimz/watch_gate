# MITRE ATT&CK T1552 — Unsecured Credentials

## Descripción

Los adversarios buscan en sistemas comprometidos credenciales almacenadas
de forma insegura: contraseñas, tokens de API, claves privadas, secretos
de nube. En el contexto de la cadena de suministro esto es habitualmente
el OBJETIVO FINAL — un paquete malicioso o un paso de build comprometido no
suele querer la máquina del desarrollador por sí misma, sino las
credenciales que esa máquina o ese runner de CI/CD tiene a mano para
pivotar hacia el registro de paquetes, el proveedor de nube o el resto de
la organización.

Sub-técnicas relevantes para código y CI/CD:

- **T1552.001 Credentials In Files**: secretos en ficheros de
  configuración, `.env`, `~/.aws/credentials`, `~/.npmrc`, `~/.pypirc`,
  historiales de shell. El caso típico de un stealer inyectado por un
  paquete npm/PyPI: recorre el `$HOME` en busca de estos ficheros.
- **T1552.004 Private Keys**: claves SSH (`~/.ssh/id_*`), claves de firma
  de código, certificados TLS, claves GPG. El compromiso de PyTorch/
  torchtriton exfiltraba las primeras líneas de `~/.ssh/*` (ver
  `pytorch_torchtriton_dependency_confusion.md`).
- **T1552.005 Cloud Instance Metadata API**: desde un runner de CI/CD o un
  contenedor en la nube, consultar el endpoint de metadatos
  (`169.254.169.254`) para robar las credenciales temporales del rol IAM
  asociado — escalada directa de "ejecuté código en el build" a "tengo
  credenciales de nube de la organización".
- **T1552.007 Container API**: robar tokens de service account de
  Kubernetes desde dentro de un pod (el caso litellm intentaba desplegar
  pods privilegiados y extraer secretos del clúster, ver
  `litellm_pypi_trivy_cicd_compromise.md`).

## Ejemplos de procedimiento (patrón, no exhaustivo)

- Stealers de npm/PyPI que en su `postinstall`/`.pth`/import recorren el
  home buscando `.env`, `.npmrc`, `.aws/credentials`, wallets de
  criptomonedas y variables de entorno, y exfiltran lo encontrado.
- El worm Shai-Hulud (npm, 2025) recolectaba credenciales de NPM, GitHub y
  nube y las reutilizaba para auto-propagarse a más paquetes del
  desarrollador víctima — credenciales robadas como combustible de la
  propagación (ver `shai_hulud_npm_worm_2025.md`).
- GlassWorm (extensiones VS Code, 2025) robaba credenciales de NPM, GitHub
  y Git más 49 extensiones de carteras de criptomonedas (ver
  `glassworm_vscode_extension_invisible_unicode.md`).

## Mitigaciones

- **M1041 Encrypt Sensitive Information** / gestores de secretos: no dejar
  secretos en texto plano en ficheros ni en variables de entorno del
  runner; usar un vault con acceso auditado.
- **M1037 Filter Network Traffic**: restringir el acceso saliente de los
  runners de CI/CD y del endpoint de metadatos de nube (IMDSv2, hop limit
  1) — corta el pivote aunque el código malicioso ya se ejecute.
- **M1027 Password Policies** / credenciales efímeras: tokens de vida
  corta y con el mínimo alcance (una API key de WatchGate atada a UN repo,
  no a toda la organización, es este principio aplicado).
- **M1017 User Training**: no imprimir secretos en logs de CI (donde
  quedan legibles para cualquiera con acceso al historial de builds).

## Patrón a vigilar

En un diff: código nuevo (sobre todo en una dependencia o en un script de
build) que LEE rutas de credenciales conocidas (`~/.ssh`, `.env`,
`.aws/credentials`, `.npmrc`, `.pypirc`, `~/.gitconfig`), consulta el
endpoint de metadatos de nube (`169.254.169.254`), o lee variables de
entorno en bloque y las envía por red — especialmente si el propósito
declarado del paquete no tiene nada que ver con credenciales.

Técnica MITRE ATT&CK relacionada: T1552 (y sus sub-técnicas .001/.004/
.005/.007); objetivo final frecuente de T1195.001/T1195.002; suele
combinarse con T1048 (Exfiltration Over Alternative Protocol — DNS/HTTPS)
y T1102 (Web Service como canal de C2/exfiltración).
