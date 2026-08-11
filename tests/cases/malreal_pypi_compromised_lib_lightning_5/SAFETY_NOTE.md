# Aviso: este fixture contiene malware real

`after/start.py` es el payload real (parte del dropper) extraído del
dataset público
[DataDog/malicious-software-packages-dataset](https://github.com/DataDog/malicious-software-packages-dataset)
(paquete `lightning` v2.6.3, comprometido de verdad), descifrado con la
contraseña estándar que el propio dataset documenta (`infected`, ver su
README) -- no un secreto, es la convención habitual en datasets de malware
para que un antivirus no lo detone al escanear el repositorio.

Este fichero vivía en `lightning/_runtime/start.py` junto a
`router_runtime.js` (11.4 MB, ofuscado con el mismo patrón de array de
cadenas visto en otros casos de este dataset, con contenido consistente
con robo de tokens/credenciales). No se incluye `router_runtime.js` en
este fixture -- el propio `start.py` ya es suficiente evidencia por sí
solo (descarga el runtime `bun` de una release de GitHub si no está
presente, y lo ejecuta contra el script sin verificar su contenido, con
`stdout`/`stderr` silenciados) y coincide con el mismo patrón dropper que
otros 5 casos ya confirmados maliciosos en este mismo repo de tests
(`setup_bun.js`, en `malreal_npm_compromised_lib_*`).

**Nunca ejecutar este código.** No se ha intentado deofuscar ni ejecutar
`router_runtime.js`.

WatchGate nunca ejecuta el contenido de un diff (`pipeline_runner.py` solo
construye un `git diff` de texto y se lo pasa a los analizadores) -- este
fixture es seguro dentro del flujo normal de la suite de tests. El riesgo
sería ejecutarlo fuera de ese flujo (p. ej. `python start.py` a mano).

Ver `docs/evaluacion_ia/ground_truth_dudoso_dataset_datadog.md` para el
contexto completo de por qué se sustituyó el fichero original de esta
fixture (`subprocess_script.py`, código real y benigno de PyTorch
Lightning) por este.
