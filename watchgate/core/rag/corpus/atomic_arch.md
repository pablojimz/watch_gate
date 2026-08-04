# Caso: campaña "Atomic Arch" contra paquetes del AUR

## Resumen

Campaña de 2024-2025 en la que se comprometieron más de 400 paquetes del
Arch User Repository (AUR) — el repositorio de paquetes mantenidos por la
comunidad para Arch Linux, donde cualquier usuario puede publicar o adoptar el
mantenimiento de un `PKGBUILD`. Los atacantes tomaron el control de paquetes
huérfanos o poco mantenidos y añadieron payloads maliciosos a sus scripts de
instalación.

## Vector de introducción

- El AUR no tiene el mismo nivel de revisión que un repositorio oficial: los
  `PKGBUILD` (scripts de shell que definen cómo compilar/instalar un paquete)
  se ejecutan con privilegios del usuario que instala, incluyendo funciones
  `pre_install`, `post_install`, `pre_upgrade`, que son puntos de ejecución de
  código arbitrario.
- Los atacantes falsificaron nombre y correo de commit para simular
  continuidad con el mantenedor original del paquete, de forma que un
  histórico de "quién ha tocado esto" no levantaba sospechas por sí solo.
- El payload típico: una llamada de red (`curl`/`wget`) a un dominio de
  apariencia legítima dentro de una función de instalación, seguida de
  ejecución (`curl ... | bash`) o escritura en rutas sensibles
  (`~/.ssh/authorized_keys`, modificación de `~/.bashrc` para persistencia).
- En algunos casos el cambio se introdujo como un "bump" de versión rutinario
  (subir de v1.2.3 a v1.2.4), un tipo de PR que habitualmente recibe muy poco
  escrutinio porque "solo" cambia un número de versión y checksums.

## Por qué es relevante para WatchGate

- Es el caso de referencia para la capa de **reputación**: la identidad
  declarada del autor (nombre/email del commit) puede coincidir con la del
  mantenedor legítimo aunque la cuenta real que ejecuta el push sea nueva, sin
  contribuciones previas reales o sin verificación de email — señales que
  *sí* son observables aunque el nombre/email se falsifiquen.
- Confirma que los "bump de versión" rutinarios no deben tratarse como
  automáticamente de bajo riesgo: un cambio pequeño en líneas pero con una
  llamada de red nueva en un script de build/instalación es exactamente el
  patrón que debe forzar revisión (ver `shortcircuit.py`, patrones que fuerzan
  la capa semántica: `PKGBUILD$`).

Técnica MITRE ATT&CK relacionada: T1195 (Supply Chain Compromise), T1548
(Abuse Elevation Control Mechanism) cuando el payload persigue escalada de
privilegios o persistencia tras la instalación.
