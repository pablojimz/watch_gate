# Aviso: este fixture contiene malware real

`after/package.json` y `after/bundle.js` son el payload real extraído del
dataset público
[DataDog/malicious-software-packages-dataset](https://github.com/DataDog/malicious-software-packages-dataset)
(paquete `tvi-cli` v0.1.5, comprometido de verdad), descifrado con la
contraseña estándar que el propio dataset documenta (`infected`, ver su
README) -- no un secreto, es la convención habitual en datasets de malware
para que un antivirus no lo detone al escanear el repositorio.

Este es el 5º caso de esta misma familia de ground truth no fiable, no
documentado en el hallazgo original (`docs/evaluacion_ia/ground_truth_dudoso_dataset_datadog.md`)
porque apareció al regenerar `docs/validation_report.md` después de
arreglar los otros 4. `bundle.js` (3.7 MB) es prácticamente el mismo
payload que el de `malreal_npm_compromised_lib_graphql-sequelize-teselagen_14`
(primeros ~5 KB idénticos byte a byte, MD5 distinto en el resto -- misma
campaña/familia de malware, no una coincidencia) -- lógica de resolución
de credenciales tipo AWS (`resolveWebIdentityCredentials`). `package.json`
referencia `"scripts": {"postInstall": "node bundle.js"}` (nótese la `I`
mayúscula -- no es el nombre exacto del hook real de npm,
`postinstall`; puede que el propio malware tenga un fallo o dependa de
otra vía de invocación no verificada aquí).

**Nunca ejecutar `npm install`/`node` sobre este fixture.** No se ha
llegado a analizar el bundle completo, solo a confirmar la coincidencia
con el payload ya verificado del caso teselagen.

WatchGate nunca ejecuta el contenido de un diff (`pipeline_runner.py` solo
construye un `git diff` de texto y se lo pasa a los analizadores) -- este
fixture es seguro dentro del flujo normal de la suite de tests.

El fichero original de esta fixture (`middleware.ts`, un middleware CORS
de Next.js genérico y benigno, parte de las plantillas de scaffolding que
`tvi-cli` genera en proyectos nuevos -- nunca se ejecuta el propio CLI)
queda sustituido por el payload real.
