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

## Patrón a vigilar

Lógica condicional sobre arquitectura/compilador en ficheros de test o
build, o datos de test binarios sin relación con ningún caso documentado.

Técnica MITRE ATT&CK relacionada: T1195.002 (Compromise Software Supply
Chain), T1027 (Obfuscated Files or Information).
