# MITRE ATT&CK T1027 — Obfuscated Files or Information

**Táctica:** Defense Evasion. **Plataformas:** ESXi, Linux, Network Devices,
Windows, macOS.

## Descripción

El adversario usa cifrado, codificación u ofuscación para dificultar el
descubrimiento o análisis de ejecutables y ficheros en sistemas o en
tránsito. Sirve como mecanismo de sigilo frente a herramientas defensivas.
Los payloads pueden comprimirse, empaquetarse o cifrarse durante el acceso
inicial o en etapas posteriores; a veces requiere acción del usuario para
abrir y desofuscar el fichero. Partes de ficheros pueden codificarse para
ocultar cadenas de texto plano, y los payloads pueden dividirse en ficheros
benignos separados que solo revelan funcionalidad maliciosa al
recombinarse. La ofuscación de comandos usando variables de entorno y
semántica específica de la plataforma ayuda a evadir detecciones basadas en
firmas.

## Sub-técnicas (18 en total)

T1027.001 Binary Padding · T1027.002 Software Packing · T1027.003
Steganography · T1027.004 Compile After Delivery · T1027.005 Indicator
Removal from Tools · T1027.006 HTML Smuggling · T1027.007 Dynamic API
Resolution · T1027.008 Stripped Payloads · T1027.009 Embedded Payloads ·
T1027.010 Command Obfuscation · T1027.011 Fileless Storage · T1027.012 LNK
Icon Smuggling · T1027.013 Encrypted/Encoded File · T1027.014 Polymorphic
Code · T1027.015 Compression · T1027.016 Junk Code Insertion · T1027.017
SVG Smuggling · T1027.018 Invisible Unicode.

## Mitigaciones (MITRE)

- **M1049 — Antivirus/Antimalware**: detección y cuarentena automáticas de
  ficheros sospechosos (p. ej. AMSI en Windows 10+ para analizar comandos
  tras su procesamiento).
- **M1047 — Audit**: revisión periódica de ubicaciones de almacenamiento
  *fileless* (Registro, repositorio WMI) para identificar datos anómalos.
- **M1040 — Behavior Prevention on Endpoint**: reglas de reducción de
  superficie de ataque (Windows 10+) para prevenir ejecución de payloads
  potencialmente ofuscados.
- **M1017 — User Training**: restringir los puntos de entrada a sistemas
  de despliegue de software a personal autorizado.

## Estrategia de detección (MITRE)

**DET0378 — Behavioral Detection of Obfuscated Files or Information**

- **AN1064**: correlación entre ejecución de scripts y creación de formatos
  codificados/comprimidos, con sintaxis de comando anómala.
- **AN1065**: detecta uso de `gzip`, `base64`, `tar`, `openssl` en scripts
  que codifican ficheros tras el *staging*.
- **AN1067**: identifica transferencia de ficheros base64/uuencoded sobre
  HTTP, FTP o protocolos personalizados.

## Ejemplos de procedimiento (uso real por grupos de amenaza)

- **Sandworm Team** (2016 Ukraine Electric Power Attack) — código
  fuertemente ofuscado en Industroyer, dentro de una puerta trasera
  disfrazada de Bloc de notas de Windows.
- **AppleJeus** (Ataque a la cadena de suministro de 3CX) — payloads
  cifrados con AES-256 GCM para los datos de ICONICSTEALER y VEILEDSIGNAL.
- **APT41** — binarios protegidos con VMProtect; fragmentó los binarios
  DEADEYE y KEYPLUG en múltiples secciones de disco para evasión.
- **SUNBURST** (compromiso de SolarWinds Orion) — algoritmo FNV-1a + XOR
  para ofuscar información del sistema.
- **RedCurl** — cifrado de cadenas, codificación base64 de comandos
  PowerShell, PyArmor para ofuscar código, y renombrado de ficheros como
  herramientas legítimas.

## Patrones observables en un diff de PR (nota WatchGate)

- Cadenas base64 largas y contiguas (más de ~200 caracteres) embebidas en
  código fuente, ficheros de configuración o de test que normalmente no
  contendrían datos binarios codificados.
- Secuencias hexadecimales largas con alta entropía (shellcode codificado),
  especialmente en ficheros que no son binarios por naturaleza (`.py`,
  `.js`, `.yml`, scripts de shell).
- Uso de `eval()`, `exec()`, `Function(...)` (JavaScript) sobre una cadena
  reconstruida en tiempo de ejecución (concatenación de fragmentos,
  decodificación base64 seguida de ejecución), en vez de código estático
  legible.
- Payloads distribuidos en "capas": un fragmento inocuo en un commit, otro
  en un commit posterior, que solo cobran sentido combinados (como en
  xz-utils, donde el payload real vivía repartido entre datos de test
  binarios y lógica condicional en scripts `m4`).
- Ficheros de test/datos (`tests/files/*`, fixtures) con contenido binario
  que no corresponde a ningún caso de test documentado en el propio PR.
- Dentro de un **mismo PR**, un fichero nuevo con la lógica real del
  payload, combinado con una modificación mínima —a veces una sola línea—
  en un fichero ya existente que se limita a importarlo y ejecutarlo:

```
+ app/_startup_check.py   (nuevo, ~15 líneas: exec(fetch(url)) en verify())
  app/__init__.py         (modificado, +1 línea: "from ._startup_check import verify; verify()")
```

El fichero nuevo concentra toda la lógica y llamaría la atención si se
revisara aislado; la modificación real que lo activa es una sola línea en
un fichero ya existente, fácil de pasar por alto en un diff que a simple
vista "solo añade un import".

La capa **estática** implementa reglas YARA explícitas para blobs base64
largos y secuencias hexadecimales de alta entropía (Shannon > 4.5
bits/byte). La capa **semántica** trata con especial atención cualquier
construcción `eval`/`exec` sobre entrada no literal: el patrón "código que
genera o decodifica código" es en sí mismo una señal de ofuscación,
independientemente de si el contenido decodificado resulta benigno.
