# Técnica: "Trojan Source" — caracteres Unicode bidireccionales (CVE-2021-42574)

## Resumen

En noviembre de 2021, investigadores de la Universidad de Cambridge
(Nicholas Boucher y Ross Anderson) publicaron "Trojan Source: Invisible
Vulnerabilities", una técnica que explota los caracteres de control Unicode
bidireccional (*bidi*, como `U+202E RIGHT-TO-LEFT OVERRIDE` o
`U+2066`-`U+2069`) — pensados originalmente para mezclar texto de idiomas
que se leen de derecha a izquierda (árabe, hebreo) con texto latino. Estos
caracteres pueden reordenar visualmente el código en un editor o en la vista
de un diff **sin cambiar el orden real en que el compilador/intérprete lo
procesa**: lo que un revisor humano *ve* en pantalla no es lo que el
compilador *ejecuta*.

Se asignaron múltiples CVEs a compiladores e intérpretes afectados (C, C++,
C#, Go, Java, JavaScript, Python, Rust, entre otros) por no rechazar o
señalizar estos caracteres por defecto.

## Cómo se ve (o no se ve) en un diff

El ataque típico: un comentario o un string literal contiene caracteres bidi
que hacen que código *después* del comentario/string parezca estar *dentro*
de él visualmente, cuando en realidad el compilador lo trata como código
activo. Ejemplo conceptual (los caracteres de control no son visibles como
texto, solo alteran el orden de renderizado):

```
// Comentario normal ‮ if (usuario == "admin") ⁦ acceso_concedido = true; ⁩
```

Visualmente, un revisor puede leer el comentario como una única línea
inocua; el compilador ve una condición real activa fuera del comentario. En
un diff de GitHub/GitLab renderizado en el navegador, el efecto es el mismo:
el highlighting de sintaxis y el orden visual no reflejan la semántica real.

## Comprobación imprescindible antes de puntuar: ¿el payload está de verdad fuera del comentario?

La sola presencia de caracteres de control bidireccional es señal suficiente
para investigar con cuidado, pero **no basta por sí sola para confirmar que
el ataque funciona en un diff concreto**. En lenguajes con comentarios de
una sola línea que terminan en el salto de línea físico (`#` en Python,
`//` en C/C++/JS/Go), **todo el contenido posterior al marcador de
comentario dentro de esa misma línea física es inerte**, con total
independencia de qué caracteres Unicode contenga — ningún carácter bidi
puede hacer que el tokenizer trate texto como código activo si sigue
estando, en el flujo de bytes real (no en el orden visual), dentro de la
misma línea comentada. El ataque real de Trojan Source requiere que el
código activo esté genuinamente en un token o línea *distinta* del
comentario en el flujo de bytes, con los caracteres bidi solo alterando
cómo se **renderiza** esa separación real, no creándola de la nada.

Antes de asignar una puntuación alta solo por reconocer esta técnica,
comprueba: ¿el texto "oculto" está en la misma línea física que el
marcador de comentario (`#`, `//`), o en una línea/token distinto? Solo en
el segundo caso el payload puede ejecutarse de verdad.

## Patrón a vigilar

Presencia de caracteres de control bidireccional Unicode (rango
`U+202A`-`U+202E`, `U+2066`-`U+2069`) en un fichero que no sea
explícitamente de datos/i18n.

Técnica MITRE ATT&CK relacionada: T1027 (Obfuscated Files or Information).
