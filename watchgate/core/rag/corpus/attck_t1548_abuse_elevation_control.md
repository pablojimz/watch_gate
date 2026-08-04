# MITRE ATT&CK T1548 — Abuse Elevation Control Mechanism

## Descripción

El adversario aprovecha mecanismos legítimos de control de elevación de
privilegios para ejecutar código con permisos superiores a los que tendría de
otro modo, o para evadir controles de detección que dependen de ese mismo
mecanismo. En un contexto de scripts de instalación/build, esto normalmente
significa escribir en rutas que requieren o conceden privilegios elevados, o
modificar mecanismos de autenticación/autorización del propio sistema.

## Patrones observables en un diff de PR

- Escritura directa a rutas sensibles del sistema: `/etc/passwd`,
  `/etc/sudoers`, `/etc/sudoers.d/*`, `~/.ssh/authorized_keys`,
  `~/.bashrc`/`~/.zshrc` (para persistencia de comandos en cada sesión de
  shell nueva).
- Añadir claves SSH públicas no reconocidas a `authorized_keys` durante un
  script de instalación (`post_install` de un `PKGBUILD`, `postinstall` de un
  paquete npm), lo que concede acceso remoto persistente al atacante.
- Modificación de permisos de ficheros/directorios (`chmod`, `chown`) hacia
  valores más permisivos de lo necesario para la funcionalidad declarada del
  paquete.
- Scripts de instalación que se autoconceden ejecución con `sudo`/`doas` sin
  que el propósito del paquete lo justifique (p. ej. un paquete de utilidad
  de línea de comandos que no necesita privilegios de administrador para
  funcionar).

## Relevancia para WatchGate

La capa **estática** incluye una regla explícita
(`privilege-escalation-write`) para detectar escritura a estas rutas
sensibles. Es una señal de severidad alta casi sin excepciones legítimas
plausibles en el contexto de un script de instalación de un paquete de
aplicación — a diferencia de otras señales (como una llamada de red en un
script de build), donde sí existen usos legítimos que la capa semántica debe
saber distinguir, aquí la combinación "script de instalación de paquete +
escritura a `authorized_keys` o `sudoers`" es en la práctica siempre
indicativa de intención maliciosa (persistencia o escalada de privilegios).
