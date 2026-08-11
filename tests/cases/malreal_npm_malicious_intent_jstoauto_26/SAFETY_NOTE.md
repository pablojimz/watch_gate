# Aviso: este fixture contiene malware real

`after/pino.js` es el entry point real extraído del dataset público
[DataDog/malicious-software-packages-dataset](https://github.com/DataDog/malicious-software-packages-dataset)
(paquete `jstoauto` v5.1.0, malicioso desde su publicación), descifrado con
la contraseña estándar que el propio dataset documenta (`infected`, ver su
README) -- no un secreto, es la convención habitual en datasets de malware
para que un antivirus no lo detone al escanear el repositorio.

`jstoauto` es un clon de la librería `pino` (logger real y popular de npm)
con el entry point (`pino.js`, el campo `main` de su `package.json`)
troyanizado: en vez de la lógica real del logger, hace
`require('./lib/lserver.js')` y ejecuta ese módulo en cada llamada a
`pino()`. `lib/lserver.js` (142 KB, ofuscado con el mismo patrón de array
de cadenas + evaluación indirecta visto en otros casos de este dataset) se
extrajo y se leyó como texto para confirmar el hallazgo, pero
deliberadamente NO se incluye en este fixture: al añadirlo, el diff supera
el límite de tamaño que se le pasa al LLM y el fichero se trunca, lo que
hacía que la capa semántica devolviera "incertidumbre" en vez de
"malicioso" (no podía revisar el contenido completo). `pino.js` solo ya es
evidencia suficiente y autocontenida -- un logger que no loguea nada y en
su lugar ejecuta un módulo con nombre no relacionado en cada llamada.

WatchGate nunca ejecuta el contenido de un diff (`pipeline_runner.py` solo
construye un `git diff` de texto y se lo pasa a los analizadores) -- este
fixture es seguro dentro del flujo normal de la suite de tests. El riesgo
sería ejecutarlo fuera de ese flujo (p. ej. `node pino.js` a mano).

Ver `docs/evaluacion_ia/ground_truth_dudoso_dataset_datadog.md` para el
contexto completo de por qué se sustituyó el fichero original de esta
fixture (`tools.js`, código real y benigno de `pino` vendorizado) por este.
