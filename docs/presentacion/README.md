# Presentación WatchGate

Material para la **presentación final** (15 min: ~8 de explicación + ~7 de demo).

Para colores, tipografías, iconos/emoji y cómo mantener la coherencia visual
al añadir contenido nuevo, ver [GUIA_ESTILO.md](GUIA_ESTILO.md).

## Contenido de la carpeta

| Fichero | Qué es |
|---|---|
| `GUIA_ESTILO.md` | Docker, paleta, tipografías, iconos/emoji y convenciones TikZ — léela antes de tocar diagramas o la plantilla. |
| `WatchGate_plantilla.pptx` | **Plantilla PowerPoint** para subir a Google Slides y que el equipo la edite. Portada + índice + diapositivas-plantilla (contenido, diagrama de capas, diagrama MCP/agentes, 3 tarjetas, tabla, cierre). |
| `plantilla_pptx/build_pptx.py` | Generador de la plantilla (`python-pptx`). Editar aquí y regenerar si hay que tocar la identidad visual. |
| `diagrama_capas.tex` / `.pdf` / `.png` | **Diagrama general de capas** actualizado: 5 capas (se añade *Vulnerabilidades*), capas deterministas vs. capa semántica **opcional** (cortocircuito). |
| `diagrama_mcp_agentes.tex` / `.pdf` / `.png` | **Diagrama del flujo con agentes de IA + servidor MCP** (el tercer flujo de la pizarra, a cargo de Javi): agente en el IDE → servidor MCP (`watchgate mcp serve`) → sus 5 herramientas → mismo núcleo de WatchGate → `AgentGuidance` (`PROCEED` / `RETRY_WITH_FIX` / `BLOCK_HUMAN_REVIEW`) → PR normal o revisión humana. Iconos de `fontawesome5` (viene con el `texlive/texlive` de Docker, no hay que instalar nada aparte). |
| `diagrama_estructura.png` | Diagrama antiguo (4 capas). Lo sigue usando `main.tex`. Obsoleto para la versión final. |
| `main.tex` / `main.pdf` | Deck LaTeX/Beamer del *kickoff* (julio 2026). Se conserva como referencia; la versión final se monta sobre la plantilla `.pptx`. |
| `malaga.jpeg` | Foto de fondo de la portada. |
| `logos/watchgate_{white,navy,cyan}.{svg,png}` | Logo nuevo recoloreado. `white` para fondos oscuros (portada), `navy` para fondos claros, `cyan` de acento. Origen: `watchgate/dashboard/frontend/public/logo.svg`. |
| `logos/uma.png`, `google.png`, `virustotal.png` | Solo los usa el deck del kickoff (`main.tex`). **No** van en la presentación final. |

## Cómo regenerar

Todo se compila en Docker (no hace falta instalar LaTeX ni fuentes en la máquina).

### Diagramas (capas / MCP-agentes)

Mismo comando para ambos, cambiando el nombre del `.tex`:

```bash
cd docs/presentacion
for f in diagrama_capas diagrama_mcp_agentes; do
  docker run --rm -v "$PWD":/w -w /w texlive/texlive:latest sh -c "
    for i in 1 2 3; do pdflatex -interaction=nonstopmode -halt-on-error $f.tex; done
    gs -dSAFER -dBATCH -dNOPAUSE -sDEVICE=png16m -r300 \
       -dTextAlphaBits=4 -dGraphicsAlphaBits=4 \
       -sOutputFile=$f.png $f.pdf
  "
  rm -f $f.aux $f.log
done
```

### Plantilla .pptx

```bash
python3 -m venv /tmp/pptxvenv && /tmp/pptxvenv/bin/pip install python-pptx pillow
/tmp/pptxvenv/bin/python docs/presentacion/plantilla_pptx/build_pptx.py
# -> docs/presentacion/WatchGate_plantilla.pptx
```

### Previsualizar el .pptx como imágenes (opcional)

```bash
docker run --rm -v "$PWD":/w --entrypoint /bin/bash linuxserver/libreoffice:latest \
  -c 'cd /w && soffice --headless --convert-to pdf WatchGate_plantilla.pptx'
```

## Qué cambió respecto al kickoff

- **Capa nueva de Vulnerabilidades**: se separa de *Dependencias*. *Dependencias* se queda con
  señales de **intención maliciosa** en el PR (typosquatting, scripts de instalación, URL/Git
  directas); *Vulnerabilidades* cubre **CVEs conocidas** (OSV) en dependencias — código
  vulnerable, no necesariamente malicioso. Pesos por defecto: `static 0.25 · dependencies 0.10 ·
  vulnerabilities 0.10 · reputation 0.15 · semantic 0.40`.
- **La capa semántica (LLM) es opcional**: el cortocircuito (`shortcircuit.py`, opt-in) la omite
  cuando ya hay veredicto sin ella — hallazgo malicioso determinista de confianza alta, media
  ponderada parcial que ya no puede cruzar el umbral, sin presupuesto de tokens, o diff ya
  cacheado.
- Cada hallazgo se clasifica por naturaleza: 🚨 malicioso · ⚠️ vulnerabilidad · ❓ incertidumbre,
  con **bloqueo estricto** ante hallazgos maliciosos de confianza alta/media.
