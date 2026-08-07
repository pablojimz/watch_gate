"""Registro de capas de análisis en watchgate.core.layers.

`register_layer` (base.py) tiene efecto secundario: una capa solo aparece en
`LAYER_REGISTRY` si su módulo se ha importado al menos una vez en el proceso.
`orchestrator.py` nunca importa una capa por nombre (por diseño, A.0.0), así
que basta con importar aquí cada capa concreta -- quien importe este paquete
(o cualquier submódulo, que primero importa el paquete) las registra todas,
sin depender de qué módulo se haya importado primero por su cuenta.

IMPORTANTE si se añade una capa nueva: `orchestrator.py` filtra por
`weight > 0 and name in LAYER_REGISTRY` -- una capa con peso pero sin
importar aquí no da ningún error, simplemente se excluye en silencio de
todos los análisis reales (CLI, GitHub Action), sin que nada lo note salvo
el score final "no cuadrando". Justo lo que le pasaba a `static_layer.py`:
implementada, testeada y con peso 0.25 por defecto en `config.py`, pero
nunca se había importado aquí -- `LAYER_REGISTRY` nunca tenía "static" en
ninguna ejecución real, así que la capa estática (Semgrep/YARA) jamás
llegó a ejecutarse contra un PR de verdad, solo en sus propios tests
unitarios (que la importan directamente). Confirmado en vivo: tras
`import watchgate.core.layers` (como hacen `cli.py`/`adapters/github_action/
main.py`), `LAYER_REGISTRY` solo tenía `dependencies`/`reputation`/
`semantic`.
"""

from __future__ import annotations

import watchgate.core.layers.deps_layer as deps_layer
import watchgate.core.layers.reputation_layer as reputation_layer
import watchgate.core.layers.static_layer as static_layer
import watchgate.core.layers.vulnerabilities_layer as vulnerabilities_layer
from watchgate.core.layers._semantic import layer as semantic_layer

__all__ = [
    "deps_layer",
    "reputation_layer",
    "semantic_layer",
    "static_layer",
    "vulnerabilities_layer",
]
