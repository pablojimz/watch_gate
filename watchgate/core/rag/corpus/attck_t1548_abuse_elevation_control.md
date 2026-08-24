# MITRE ATT&CK T1548 — Abuse Elevation Control Mechanism

**Táctica:** Privilege Escalation. **Plataformas:** IaaS, Identity Provider,
Linux, Office Suite, Windows, macOS.

## Descripción

El adversario aprovecha mecanismos legítimos diseñados para controlar la
elevación de privilegios, con el fin de conseguir permisos de nivel
superior a los que tendría de otro modo. En un contexto de scripts de
instalación/build, esto normalmente significa escribir en rutas que
requieren o conceden privilegios elevados, o modificar mecanismos de
autenticación/autorización del propio sistema.

## Sub-técnicas

- **T1548.001** — Setuid and Setgid
- **T1548.002** — Bypass User Account Control
- **T1548.003** — Sudo and Sudo Caching
- **T1548.004** — Elevated Execution with Prompt
- **T1548.005** — Temporary Elevated Cloud Access
- **T1548.006** — TCC Manipulation

## Ejemplos de procedimiento

- **Raspberry Robin (S1130)** — Implementa una variante de la técnica
  `ucmDccwCOMMethod`, explotando "la puerta trasera AutoElevate de Windows
  para saltarse UAC mientras eleva privilegios".
- **UNC3886 (G1048)** — Desplegó vSphere Installation Bundles con "ficheros
  XML descriptor modificados con el `acceptance-level` fijado a `partner`,
  lo que permitía escalada de privilegios".

## Mitigaciones (MITRE)

| ID | Estrategia | Descripción |
|---|---|---|
| M1047 | Audit | Evaluar sistemas en busca de debilidades que permitan saltarse UAC. |
| M1038 | Execution Prevention | Restringir aplicaciones sin firmar; limitar ejecución a repositorios legítimos. |
| M1028 | Operating System Configuration | Minimizar bits setuid/setgid; activar `tty_tickets` de sudo. |
| M1026 | Privileged Account Management | Retirar membresía del grupo de administradores local; exigir contraseña para `sudo`. |
| M1022 | Restrict File and Directory Permissions | Restringir la edición del fichero sudoers; exigir contraseña. |
| M1051 | Update Software | Actualizaciones de software regulares. |
| M1052 | User Account Control | Mantener el nivel de aplicación de UAC más alto. |
| M1018 | User Account Management | Limitar la asunción de privilegios de cuentas cloud; exigir aprobación manual para elevación temporal. |

## Estrategia de detección (MITRE)

Cinco analíticas dirigidas a: modificaciones de registro, relaciones entre
procesos, cambios de bits setuid/setgid, uso de APIs de autorización, y
operaciones de escalada de privilegios.

## Patrones observables en un diff de PR (nota WatchGate)

- Escritura directa a rutas sensibles del sistema: `/etc/passwd`,
  `/etc/sudoers`, `/etc/sudoers.d/*`, `~/.ssh/authorized_keys`,
  `~/.bashrc`/`~/.zshrc` (persistencia de comandos en cada sesión de shell
  nueva).
- Añadir claves SSH públicas no reconocidas a `authorized_keys` durante un
  script de instalación (`post_install` de un `PKGBUILD`, `postinstall` de
  npm), concediendo acceso remoto persistente.
- Modificación de permisos (`chmod`, `chown`) hacia valores más permisivos
  de lo necesario para la funcionalidad declarada.
- Scripts de instalación que se autoconceden ejecución con `sudo`/`doas`
  sin que el propósito del paquete lo justifique.

La capa **estática** incluye una regla explícita
(`privilege-escalation-write`) para estas rutas sensibles — señal de
severidad alta casi sin excepciones legítimas plausibles en el contexto de
un script de instalación de paquete.
