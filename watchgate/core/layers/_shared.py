"""Utilidades compartidas entre capas de análisis (spec §5, §11).
 
Módulo deliberadamente pequeño y sin dependencias de ninguna capa concreta:
cualquier capa (o `shortcircuit.py`) puede importar de aquí sin crear un
ciclo de imports.
 
La spec de `deps_layer.py` (§5) también prevé mover aquí
`_run_semgrep_on_text` (reutilizada desde `static_layer.py` para analizar
scripts de instalación de paquetes) — eso es responsabilidad de quien
implemente la Línea 3 (capas estática/dependencias), no de este módulo por
ahora. Se deja documentado el hueco para no chocar con esa implementación.
"""
 
from __future__ import annotations
 
# Nombres de fichero (no rutas completas) que WatchGate reconoce como
# manifiestos de gestión de dependencias.
#
# Usado por:
# - deps_layer.py (§5, paso 1): decidir si hay algo que analizar antes de
#   consultar OSV.
# - shortcircuit.py (§11, _has_new_dependencies): una de las señales que
#   fuerza ejecutar la capa semántica igualmente.
DEPENDENCY_MANIFEST_FILENAMES: frozenset[str] = frozenset(
    {"package.json", "requirements.txt", "Pipfile", "PKGBUILD", "Cargo.toml"}
)
