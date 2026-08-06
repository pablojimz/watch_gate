"""Registro de capas de análisis en watchgate.core.layers.

`register_layer` (base.py) tiene efecto secundario: una capa solo aparece en
`LAYER_REGISTRY` si su módulo se ha importado al menos una vez en el proceso.
`orchestrator.py` nunca importa una capa por nombre (por diseño, A.0.0), así
que basta con importar aquí cada capa concreta -- quien importe este paquete
(o cualquier submódulo, que primero importa el paquete) las registra todas,
sin depender de qué módulo se haya importado primero por su cuenta.

`static_layer.py` todavía no define ninguna clase (`@register_layer`); se
añade aquí en cuanto exista algo que registrar.
"""

from __future__ import annotations

import watchgate.core.layers.deps_layer as deps_layer
import watchgate.core.layers.reputation_layer as reputation_layer
from watchgate.core.layers._semantic import layer as semantic_layer

__all__ = ["deps_layer", "reputation_layer", "semantic_layer"]
