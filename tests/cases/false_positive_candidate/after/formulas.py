import math

_ALLOWED_NAMES = {n: getattr(math, n) for n in ('sqrt', 'sin', 'cos', 'floor', 'ceil')}

def apply_template(template, values):
    return template.format(**values)

def evaluate_formula(expr, cell_values):
    """Evalua una formula de usuario (ej. 'sqrt(A1) + 2') sin builtins,
    imports ni I/O -- solo funciones matematicas permitidas y valores de celda ya calculados."""
    namespace = dict(_ALLOWED_NAMES)
    namespace.update(cell_values)
    return eval(expr, {'__builtins__': {}}, namespace)
