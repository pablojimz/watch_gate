# Guía de estilo y herramientas — Presentación WatchGate

Referencia para que cualquiera del equipo pueda tocar la plantilla o añadir un
diagrama nuevo sin romper la identidad visual ni repetir los mismos bugs de
alineación en los que ya caí yo. Ver también [README.md](README.md) para el
listado de ficheros y los comandos de regeneración.

## 1. Herramientas (todo vía Docker, nada instalado en local)

No hay LaTeX ni LibreOffice instalados en las máquinas del equipo.

| Imagen Docker | Para qué |
|---|---|
| `texlive/texlive:latest` (~9 GB) | Compilar los `.tex` (`pdflatex`) y rasterizarlos a PNG (`gs`/Ghostscript). Incluye `fontawesome5`, `XCharter`, `inconsolata`, `babel-spanish` — no hace falta instalar ningún paquete LaTeX aparte. |
| `linuxserver/libreoffice:latest` | Solo para **previsualizar** el `.pptx` como imágenes (`soffice --headless --convert-to pdf`) y comprobar que una diapositiva quedó bien antes de darla por buena. No se usa para generar nada definitivo. |

El `.pptx` en sí se genera con `python-pptx` + `pillow` en un venv de Python
normal (no hace falta Docker para eso, ver comando en el README).

## 2. Paleta de colores

La misma en LaTeX (`diagrama_capas.tex`, `diagrama_mcp_agentes.tex`, `main.tex`)
y en el `.pptx` (`build_pptx.py`):

| Nombre | Hex | Uso |
|---|---|---|
| `brandnavy` | `#002959` | Titulares, fondo de portada/cierre |
| `brandnavy2` | `#123A66` | Bordes de cajas, texto de cabecera de tarjeta |
| `brandcyan` | `#00ADCB` | Acento: regla bajo el título, iconos, marcador de viñeta |
| `paper` | `#F5F6F8` | Fondo de las diapositivas de contenido |
| `paperraised` / blanco | `#FFFFFF` | Fondo de tarjetas/cajas sobre `paper` |
| `ink` | `#14202E` | Texto principal |
| `inksoft` | `#4B586A` | Texto secundario / descripciones |
| `linecol` / `linestrong` | `#D6DCE5` / `#AAB8CA` | Líneas discontinuas, viñetas de segundo nivel |
| `boxfill` | `#E7EEF6` | Relleno de las cajas "banda" |
| `semred` | `#B23A2E` | Rojo semántico: malicioso / ROJO |
| `samber` | `#9C6B0C` | Ámbar semántico: vulnerabilidad / AMARILLO / cajas de decisión (`gate`) |
| `semgreen` | `#2E7D4F` | Verde semántico: PROCEED / VERDE |

## 3. Tipografías

| Dónde | Titulares | Cuerpo | Código/datos |
|---|---|---|---|
| Diagramas LaTeX | Negrita `brandnavy` (XCharter Bold) | XCharter | Inconsolata |
| `.pptx` | **Lato** | **PT Serif** | **Roboto Mono** |

El `.pptx` usa Lato/PT Serif/Roboto Mono (en vez de Optima/Charter/Menlo, que
usa el deck LaTeX original) porque son las que Google Slides trae nativas —
así no se rompe el diseño al subirlo y que el equipo lo edite ahí.

## 4. Iconos y emoji — que no se contradigan con el producto real

Hay **dos sistemas de iconos distintos** en este proyecto; que un diagrama use
uno u otro no es arbitrario:

### 4.1 Diagramas TikZ → iconos vectoriales de `fontawesome5`

Macro `\icn{nombre-icono}` (definida en el preámbulo, pinta el icono en
`brandcyan`). El nombre va en kebab-case, por ejemplo `\icn{robot}`,
`\icn{server}`, `\icn{bolt}`. Antes de usar un icono nuevo, comprobar que
existe en el paquete (para no romper la compilación en Docker):

```bash
docker run --rm texlive/texlive:latest sh -c \
  "grep -E '\{nombre-icono\}' /usr/local/texlive/2026/texmf-dist/tex/latex/fontawesome5/fontawesome5-mapping.def"
```

Si aparece una línea con `\faXxx{nombre-icono}...` existe. Iconos ya
verificados y en uso: `robot`, `laptop-code`, `server`, `terminal`, `bolt`,
`search`, `comments`, `check-circle`, `database`, `sitemap`, `route`,
`hand-paper`, `code-branch`, `brain`, `shield-alt` (vía `\faIcon{shield-alt}`,
sin macro dedicada en esta versión del paquete).

### 4.2 Producto real (comentario de PR, CLI, dashboard) → emoji Unicode

Esto **no** es fontawesome, es texto plano que ve un usuario real en GitHub o
en su terminal. El mapeo está fijado en el código — cualquier diagrama o
diapositiva que hable del semáforo o de la naturaleza de un hallazgo debe usar
los mismos colores (y, donde tenga sentido, el mismo emoji) para no contar una
historia distinta de la que el producto realmente muestra:

| Concepto | Emoji real (código) | Color del tema |
|---|---|---|
| Semáforo VERDE | 🟢 (`comment_template.py`) | `semgreen` |
| Semáforo AMARILLO | 🟡 | `samber` |
| Semáforo ROJO | 🔴 | `semred` |
| Hallazgo malicioso | 🚨 (`comment_template.py`, `formatters/console.py`) | `semred` |
| Hallazgo vulnerabilidad | ⚠️ | `samber` |
| Hallazgo incertidumbre | ❓ | `inksoft` (gris, sin color semántico fuerte) |
| Push aprobado (git hook) | ✅ | `semgreen` |

En los diagramas TikZ ya hechos usé un cuadrado de color (`{\color{samber}
$\blacksquare$}`) en vez del emoji real, porque `pdflatex` no siempre pinta
bien emoji Unicode a color. Si en cambio estás escribiendo una diapositiva de
**texto** en el `.pptx` (no un diagrama TikZ), ahí sí puedes teclear el emoji
real directamente — Google Slides lo renderiza sin problema y es más fiel a lo
que ve un usuario.

## 5. Convenciones del diagrama TikZ (para no repetir los bugs de alineación)

Los dos diagramas (`diagrama_capas.tex`, `diagrama_mcp_agentes.tex`) comparten
preámbulo: mismos colores, macros `\mono`/`\hd`/`\sft`/`\icn`, `\pagecolor
{paper}`, e hyphenation forzada a no partir palabras (`\hyphenpenalty=10000`)
para que el texto justificado no deje guiones feos en cajas estrechas.

Estilos TikZ reutilizables:
- `band` — caja de ancho completo (16.4cm), para los pasos principales del flujo.
- `layer` / `tool` — tarjeta pequeña en fila, para las capas/herramientas.
- `gate` — caja de decisión, borde `samber`, para puntos donde el flujo se
  ramifica (cortocircuito, `AgentGuidance`).
- `optlayer` — como `band` pero con borde discontinuo, para marcar algo
  **opcional** (la capa semántica/LLM).

**Regla de oro para que todas las flechas caigan en el mismo eje vertical**
(esto me costó dos rondas de arreglos en el diagrama de capas): todo lo que
cuelga del eje central se coloca por **cadena simétrica**, nunca calculando un
`xshift` a mano — ahí es donde metí la pata calculando mal el ancho real de la
caja (`text width` + `inner sep`, no solo `text width`). Con un número
**impar** de cajas en fila, centra la del medio en el eje (`at
([yshift=...]padre.south)`, sin `anchor`) y encadena el resto con `left=/right=
of`. Con un número **par**, pon las dos centrales a horcajadas del eje con
`anchor=east`/`anchor=west` desplazadas medio hueco cada una, y encadena hacia
fuera. El "fit" (`\node[fit=...]`) de un grupo simétrico sale centrado solo,
sin necesidad de calcular nada.

Al final de cada diagrama, esta línea fuerza la caja delimitadora de
`standalone` a ser simétrica respecto al eje central — si no, las etiquetas
laterales (la vertical rotada a la izquierda, el texto de cortocircuito a la
derecha) descuadran el recorte aunque el contenido esté perfectamente
centrado:

```latex
\path let \p1=(current bounding box.east), \p2=(current bounding box.west),
          \n1={max(\x1,-\x2)} in (\n1,0) (-\n1,0);
```

**Verificación**: antes de dar un diagrama por bueno, medir en píxeles en vez
de fiarte del ojo — con margen de error humano es fácil no ver 40-80px de
desalineación en una imagen de 3000px de ancho:

```python
from PIL import Image
im = Image.open('diagrama_x.png').convert('RGB'); W, H = im.size; px = im.load()
def arrow_x(y):
    xs = [x for x in range(W) if 70 < px[x, y][2] < 150 and px[x, y][0] < 80 and px[x, y][1] < 90]
    return (min(xs), max(xs)) if xs else None
print(W/2, arrow_x(y_de_una_fila_con_flecha))  # debe coincidir con W/2
```

## 6. Cómo añadir un diagrama nuevo

1. Copia el preámbulo completo de `diagrama_mcp_agentes.tex` (colores, macros,
   `\pagecolor`, hyphenation) a un fichero nuevo.
2. Monta el flujo con los estilos de la sección 5 (`band`/`tool`/`gate`/
   `optlayer`), aplicando la regla de la cadena simétrica desde el principio
   — no la añadas a posteriori, es más fácil diseñar centrado que recentrar.
3. Compila con el comando Docker del README, mide la alineación con el script
   de arriba, y solo entonces mírala en el visor de imágenes.
4. Para meterla en la plantilla: en `plantilla_pptx/build_pptx.py`, sigue el
   patrón de la diapositiva "Arquitectura general" — cargar el PNG con
   `PIL.Image` para sacar su proporción real y dimensionar sin deformar.
