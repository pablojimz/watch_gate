# MITRE ATT&CK T1195.002 — Compromise Software Supply Chain

## Descripción

Los adversarios pueden manipular software de aplicación antes de que llegue
al consumidor final: comprometer el código fuente de la aplicación, el
proceso o entorno de compilación (build), los mecanismos de firma, o
sustituir la versión legítima por una modificada en los servidores de
distribución o de actualización. El software comprometido llega a las
víctimas por los canales de confianza habituales — descargas oficiales,
actualizaciones automáticas, paquetes firmados — precisamente porque el
punto de manipulación está AGUAS ARRIBA de todo lo que la víctima puede
inspeccionar.

A diferencia de T1195.001 (comprometer dependencias y herramientas de
desarrollo que otros proyectos consumen), aquí el objetivo es el producto
de software en sí: el binario/paquete que el usuario final instala. Ambas
sub-técnicas comparten el rasgo definitorio de la cadena de suministro:
la víctima no cometió ningún error — confió en un canal legítimo que fue
envenenado antes de llegar a ella.

Puntos de inserción típicos, de más temprano a más tardío:

- **Código fuente**: acceso de escritura al repositorio (cuenta de
  mantenedor comprometida o infiltración social a largo plazo, como el
  caso xz-utils/"Jia Tan").
- **Proceso de build**: el compromiso más difícil de detectar — el código
  fuente que todo el mundo revisa permanece limpio; el implante se inyecta
  durante la compilación (SolarWinds/SUNSPOT interceptaba MsBuild.exe y
  sustituía un fichero fuente solo durante los segundos que duraba la
  compilación, restaurándolo después).
- **Firma y empaquetado**: robo de certificados de firma de código para
  que el binario troyanizado pase las validaciones (CCleaner, 3CX).
- **Distribución/actualización**: sustitución del instalador o del
  paquete de actualización en el servidor legítimo (NotPetya se distribuyó
  por el mecanismo de actualización del software fiscal ucraniano M.E.Doc;
  Havex/Dragonfly troyanizó instaladores de software ICS en las webs de
  los propios fabricantes).

## Ejemplos de procedimiento

- **SUNBURST / SolarWinds (S0559, 2020)**: el implante SUNSPOT vivía en el
  servidor de build de SolarWinds e inyectaba la puerta trasera en la DLL
  `SolarWinds.Orion.Core.BusinessLayer.dll` durante la compilación de
  Orion; la DLL resultante salió FIRMADA con el certificado legítimo de
  SolarWinds hacia ~18.000 organizaciones. El código en el repositorio
  nunca contuvo el implante.
- **CCleaner (2017)**: la infraestructura de build de Piriform/Avast fue
  comprometida y la versión 5.33 se distribuyó troyanizada y firmada
  (~2,3 millones de descargas), con una segunda etapa dirigida solo a un
  puñado de empresas tecnológicas concretas.
- **NotPetya / M.E.Doc (2017)**: el servidor de actualizaciones del
  software de contabilidad ucraniano M.E.Doc distribuyó el wiper NotPetya
  como si fuera una actualización legítima — el vector inicial del ataque
  destructivo más costoso registrado hasta entonces.
- **3CX (2023)**: la aplicación de escritorio 3CXDesktopApp se distribuyó
  troyanizada y firmada; el compromiso inicial de 3CX vino a su vez de
  OTRO software de terceros troyanizado (X_TRADER) — una cadena de
  suministro comprometiendo a otra.
- **xz-utils / CVE-2024-3094 (2024)**: infiltración social de años para
  obtener acceso de mantenedor e introducir el backdoor en los tarballs de
  release (no en el árbol git), activado solo durante el build de
  distribuciones concretas. Ver `xz_utils.md`.

## Mitigaciones

- **M1051 Update Software**: aplicar parches al software de la propia
  cadena de build (CI/CD, servidores de firma) — el eslabón que firma es
  el más valioso de proteger.
- **M1016 Vulnerability Scanning**: escanear el software distribuido y la
  infraestructura de build, no solo el producto final.
- **M1045 Code Signing** (verificación): validar firmas Y vigilar el uso
  de los certificados propios — una firma válida sobre un binario
  troyanizado es el sello distintivo de esta técnica, no una garantía.
- **M1046 Boot Integrity / entornos de build reproducibles**: builds
  herméticos y reproducibles hacen detectable la divergencia entre el
  fuente auditado y el binario distribuido (la detección que habría
  delatado a SUNSPOT).

## Patrón a vigilar

En un diff: cambios en scripts de build/release (`Makefile`, `m4/*.m4`,
`configure`, definiciones de pipeline CI/CD, scripts de firma o
empaquetado) que introducen pasos de red, condicionales por entorno de
compilación, o material binario/ofuscado — el código de aplicación puede
quedar intacto mientras el proceso que lo convierte en artefacto queda
envenenado. La revisión humana casi nunca mira esos ficheros con el mismo
rigor que el código de la aplicación: exactamente por eso los eligen.

Técnica MITRE ATT&CK relacionada: T1195.002; hermana de T1195.001
(Compromise Software Dependencies and Development Tools); frecuentemente
encadenada con T1553.002 (Code Signing) y T1027 (Obfuscated Files or
Information).
