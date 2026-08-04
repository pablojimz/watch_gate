# MITRE ATT&CK T1027 — Obfuscated Files or Information

## Descripción

El adversario intenta dificultar el descubrimiento o análisis de contenido
malicioso ofuscando o cifrando artefactos (ficheros, comandos, payloads) en
tránsito o en reposo. En el contexto de cadena de suministro de software,
esto se traduce en payloads que no son legibles como código fuente normal en
un diff de PR.

## Patrones observables en un diff de PR

- Cadenas base64 largas y contiguas (más de ~200 caracteres) embebidas en
  código fuente, ficheros de configuración o de test que normalmente no
  contendrían datos binarios codificados.
- Secuencias hexadecimales largas con alta entropía (shellcode codificado),
  especialmente en ficheros que no son binarios por naturaleza (scripts de
  shell, ficheros `.py`, `.js`, `.yml`).
- Uso de `eval()`, `exec()`, `Function(...)` (JavaScript) o construcciones
  equivalentes sobre una cadena reconstruida en tiempo de ejecución (p. ej.
  concatenación de fragmentos, decodificación base64 seguida de ejecución),
  en vez de código estático legible.
- Payloads distribuidos en "capas": un fragmento inocuo en un commit, otro
  fragmento en un commit posterior, que solo cobran sentido combinados (como
  en xz-utils, donde el payload real vivía repartido entre datos de test
  binarios y lógica condicional en scripts `m4`).
- Ficheros de test o de datos (`tests/files/*`, fixtures) con contenido
  binario que no corresponde a ningún caso de test documentado o referenciado
  en el propio PR.
- Dentro de un **mismo PR**, un fichero nuevo (`status: added`) que contiene
  la lógica real del payload, combinado con una modificación mínima —a veces
  una sola línea— en un fichero ya existente que se limita a importarlo y
  ejecutarlo. El fichero "sospechoso" es pequeño y nuevo (menos escrutado por
  el revisor que un diff largo sobre código conocido), y el punto de enganche
  real es casi invisible por lo corto que es.

## Ejemplo del patrón "fichero nuevo + enganche mínimo"

```
+ app/_startup_check.py   (nuevo, ~15 líneas: exec(fetch(url)) en verify())
  app/__init__.py         (modificado, +1 línea: "from ._startup_check import verify; verify()")
```

El fichero nuevo concentra toda la lógica y llamaría la atención si se
revisara aislado; la modificación real que lo activa es una sola línea en un
fichero que ya existía, fácil de pasar por alto en un diff que a simple
vista "solo añade un import".

## Relevancia para WatchGate

La capa **estática** implementa reglas YARA explícitas para blobs base64
largos y secuencias hexadecimales de alta entropía (Shannon > 4.5 bits/byte).
La capa **semántica** debe tratar con especial atención cualquier
construcción `eval`/`exec` sobre entrada no literal, incluso si el análisis
estático no la marca como crítica por sí sola — el patrón "código que genera
o decodifica código" es en sí mismo una señal de intención de ofuscar,
independientemente de si el contenido decodificado resulta benigno o no.
