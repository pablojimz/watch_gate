# Aviso: este fixture contiene malware real

`after/bundle.js` y `after/package.json` son el payload real extraído del
dataset público
[DataDog/malicious-software-packages-dataset](https://github.com/DataDog/malicious-software-packages-dataset)
(paquete `graphql-sequelize-teselagen` v5.3.8, comprometido de verdad),
descifrado con la contraseña estándar que el propio dataset documenta
(`infected`, ver su README) -- no un secreto, es la convención habitual en
datasets de malware para que un antivirus no lo detone al escanear el
repositorio.

**Nunca ejecutar `npm install`/`node` sobre este fixture.** `package.json`
tiene `"scripts": {"postinstall": "node bundle.js"}` -- se ejecutaría solo
con `npm install`, sin que nadie lo invoque explícitamente. `bundle.js`
(3.7 MB) es un bundle webpack real que incluye lógica de resolución de
credenciales tipo AWS (`resolveWebIdentityCredentials`) -- confirmado
leyendo el texto, sin llegar a ejecutarlo ni analizar el bundle completo.

WatchGate nunca ejecuta el contenido de un diff (`pipeline_runner.py` solo
construye un `git diff` de texto y se lo pasa a los analizadores) -- este
fixture es seguro dentro del flujo normal de la suite de tests. El riesgo
sería ejecutarlo fuera de ese flujo (p. ej. `npm install` a mano sobre
`after/`).

Ver `docs/evaluacion_ia/ground_truth_dudoso_dataset_datadog.md` para el
contexto completo de por qué se sustituyó el fichero original de esta
fixture (`base64.js`, benigno) por este.
