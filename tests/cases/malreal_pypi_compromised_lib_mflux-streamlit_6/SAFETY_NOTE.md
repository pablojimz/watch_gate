# Aviso: este fixture contiene malware real

`after/_index.js` es el payload real extraído del dataset público
[DataDog/malicious-software-packages-dataset](https://github.com/DataDog/malicious-software-packages-dataset)
(paquete `mflux-streamlit` v0.0.4, comprometido de verdad), descifrado con
la contraseña que el propio dataset documenta como estándar (`infected`,
ver su README) -- no un secreto, es la convención habitual en datasets de
malware para que un antivirus no lo detone al escanear el repositorio.

**Nunca ejecutar este fichero.** Es JavaScript real, ofuscado en dos capas
(array de códigos de carácter + cifrado César ROT-19, que al decodificarse
revela un loader Node.js que descifra más payload con AES-128-GCM usando
claves embebidas en el propio código) -- confirmado leyendo el texto
decodificado, sin llegar a descifrar ni ejecutar la capa final.

WatchGate nunca ejecuta el contenido de un diff (`pipeline_runner.py` solo
construye un `git diff` de texto y se lo pasa a los analizadores) -- este
fichero es seguro dentro del flujo normal de la suite de tests. El riesgo
sería ejecutarlo fuera de ese flujo (p. ej. `node after/_index.js` a mano).

Ver `docs/evaluacion_ia/ground_truth_dudoso_dataset_datadog.md` para el
contexto completo de por qué se sustituyó el fichero original de esta
fixture (`main.py`, benigno) por este.
