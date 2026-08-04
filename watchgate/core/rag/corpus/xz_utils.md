# Caso: backdoor en xz-utils / liblzma (CVE-2024-3094)

## Resumen

En marzo de 2024 se descubrió una puerta trasera introducida deliberadamente en
`liblzma` (parte del proyecto `xz-utils`), una librería de compresión usada
como dependencia transitiva de `openssh-server` en muchas distribuciones Linux
a través de `libsystemd`/`sshd`. El backdoor permitía a un atacante con una
clave privada concreta ejecutar código arbitrario a través de conexiones SSH,
saltándose la autenticación.

## Vector de introducción

El atacante ("Jia Tan") se ganó la confianza del mantenedor original durante
más de dos años mediante contribuciones legítimas y crecientes, hasta obtener
acceso de mantenedor. El propio backdoor no se introdujo como código Python/C
legible en el repositorio git, sino:

- Ofuscado dentro de ficheros de test binarios aparentemente inocuos
  (`tests/files/bad-3-corrupt_lzma2.xz` y similares), que solo se activaban
  durante el proceso de *build* (`m4/build-to-host.m4`), no en el código
  fuente que un revisor humano leería normalmente en un diff de PR.
- El script de build (`autogen.sh`/`configure`) contenía lógica condicional
  que solo activaba el payload si se cumplían condiciones muy específicas del
  entorno de compilación (arquitectura x86-64, enlazador `gcc`/`clang`,
  empaquetado `.deb`/`.rpm`), dificultando su detección en entornos de CI
  genéricos o de desarrollo.
- La ofuscación usaba compresión y XOR sobre los payloads embebidos, de forma
  que un `grep` simple sobre el diff no encontraba cadenas sospechosas.

## Por qué es relevante para WatchGate

- El cambio "parece" legítimo si se mira solo el mensaje de commit y el
  historial del autor (repuntación aparentemente sólida, acumulada durante
  años) — de ahí la necesidad de evaluar el *contenido* del cambio con
  independencia de la reputación declarada.
- El payload vivía en scripts de *build* (`Makefile`, `m4/*.m4`,
  `configure`) y en datos de test binarios, no en el código de la aplicación
  — un patrón a vigilar especialmente en la capa estática (llamadas de red o
  ejecución condicional dentro de ficheros de build) y en la capa semántica
  (¿por qué un fichero de test de compresión necesita lógica condicional
  sobre la arquitectura del compilador?).
- La introducción fue gradual y a lo largo de múltiples PRs pequeños y
  aparentemente inofensivos, no un único cambio grande y evidente.

Técnica MITRE ATT&CK relacionada: T1195.002 (Compromise Software Supply
Chain), T1027 (Obfuscated Files or Information).
