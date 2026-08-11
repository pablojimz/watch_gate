# Ground truth no fiable en algunos casos `malreal_*` (dataset DataDog)

Hallazgo real, verificado descargando el dataset de origen -- no una
suposición. Al menos 4 de los casos `class=malicious` de
`tests/cases/malreal_*_compromised_lib_*`/`malicious_intent_*` contaban
como "fallo" en la suite de validación (`tests/integration/test_cases.py`)
sin que WatchGate estuviera fallando de verdad: el fichero que quedó en el
fixture de test era código legítimo y benigno, no el payload malicioso real
del paquete comprometido. Uno de los 4 (`mflux-streamlit_6`) ya se ha
arreglado de verdad -- ver "Casos resueltos" más abajo -- quedan 3
pendientes.

## Cómo se descubrió

Cada caso `malreal_*` referencia en su `source.json` un ZIP concreto del
repositorio público [DataDog/malicious-software-packages-dataset](https://github.com/DataDog/malicious-software-packages-dataset)
(la release completa de un paquete real que fue comprometido). El fixture
de este repo (`tests/cases/<caso>/after/`) contiene solo UN fichero,
presumiblemente muestreado de ese ZIP -- pero un paquete comprometido real
tiene decenas o cientos de ficheros, y solo algunos (a veces uno solo)
contienen el código inyectado.

Verificado descargando el ZIP real de `mflux-streamlit` (referenciado por
`tests/cases/malreal_pypi_compromised_lib_mflux-streamlit_6/source.json`):
contiene un fichero `src/_index.js` de **5.2 MB** -- un tamaño absurdo para
un paquete Python de un `streamlit` wrapper -- presente SOLO en la copia
"instalada" del paquete, ausente del código fuente limpio original
(`sources/mflux-streamlit/`) del mismo ZIP. Ese fichero está **protegido
con contraseña** dentro del ZIP -- la convención estándar en datasets de
malware para que un antivirus no lo detone por accidente al escanear el
repositorio. El fixture de este repo, en cambio, contiene `src/main.py`
(17 líneas, un wrapper estándar de `streamlit run` sin nada sospechoso) --
casi con toda seguridad porque el proceso que generó la fixture no pudo
extraer el fichero cifrado y cayó a uno legible cualquiera.

En un primer momento no se intentó descifrar el payload real de
`mflux-streamlit` -- no hacía falta para confirmar el problema, y es
preferible no manipular una muestra de malware real sin necesidad
concreta. Ese caso concreto se retomó después (ver "Casos resueltos" más
abajo); los otros 3 siguen sin descifrar.

## Casos pendientes (leyendo el fichero `after/` real, no solo `expected.json`)

| Caso | Fichero en el fixture | Qué es de verdad |
|---|---|---|
| `malreal_npm_compromised_lib_graphql-sequelize-teselagen_14` | `base64.js` | Dos funciones `base64()`/`unbase64()` con `Buffer` -- 13 líneas, nada más. |
| `malreal_npm_malicious_intent_jstoauto_26` | `tools.js` | Código fuente real de la librería `pino` (logger npm real y popular), vendorizado tal cual. |
| `malreal_pypi_compromised_lib_lightning_5` | `subprocess_script.py` | Código real con licencia Apache de PyTorch Lightning -- lanzador de procesos multi-nodo estándar. |

Cada uno tiene un `KNOWN_ISSUE.md` en su directorio apuntando aquí. Falta
verificar si comparten el mismo patrón que `mflux-streamlit` (fichero
grande y sospechoso, protegido con contraseña, presente solo en la copia
"instalada" del ZIP) antes de intentar el mismo arreglo.

## Casos resueltos

`malreal_pypi_compromised_lib_mflux-streamlit_6`: se recuperó el payload
real. El ZIP de origen usa la contraseña estándar que DataDog documenta en
el README de su propio dataset (`infected` -- una convención pública, no
un secreto, pensada para que un antivirus no detone la muestra al escanear
el repositorio). Con esa contraseña se extrajo `src/_index.js` (5.2 MB) y
se leyó su contenido como texto, sin ejecutarlo en ningún momento: dos
capas de ofuscación (array de códigos de carácter + cifrado César ROT-19,
que al decodificar revela un loader Node.js que descifra más payload
embebido con AES-128-GCM y claves hardcodeadas). No se llegó a descifrar
esa última capa -- no hacía falta, el contenido ya decodificado es
suficiente evidencia de intención maliciosa real.

El fixture (`tests/cases/malreal_pypi_compromised_lib_mflux-streamlit_6/`)
se actualizó para usar `after/_index.js` (el payload real) en vez de
`after/main.py` (el wrapper benigno). `expected.json` no cambió --ya
decía `rojo`/malicioso, correctamente. Ver
`tests/cases/malreal_pypi_compromised_lib_mflux-streamlit_6/SAFETY_NOTE.md`
para el aviso de manejo del fichero. Verificado con
`poetry run pytest tests/integration/test_cases.py -m integration -k mflux`:
WatchGate ahora detecta el caso correctamente (antes fallaba con
verde/benigno sobre el `main.py` benigno).

Contraejemplo real, para que quede claro que NO todos los `compromised_lib`
están mal etiquetados: `malreal_pypi_compromised_lib_durabletask_0`
(`__init__.py`) SÍ contiene el payload real e inequívoco -- descarga un
`.pyz` de un dominio sospechoso y lo ejecuta en segundo plano al importar
el paquete -- y WatchGate lo detecta correctamente. Lo mismo
`malreal_pypi_compromised_lib_telnyx_2`/`_4` (`_client.py`, exfiltración
esteganográfica en un WAV + `exec(base64.b64decode(...))`) y los 5 casos
que comparten `setup_bun.js` (dropper que descarga e instala un runtime y
ejecuta un script externo sin verificar). El problema es específico de
paquetes donde el payload real quedó fuera del fichero muestreado, no de
la categoría `compromised_lib` en general.

## Por qué no se ha "arreglado" tocando `expected.json`

Cambiar el veredicto esperado a benigno sería tan poco honesto como dejarlo
en malicioso: el PAQUETE sí fue comprometido de verdad (hay CVE/advisory
real detrás de cada caso), solo que el fichero concreto de la fixture no
es donde vive el payload. La fixture no representa bien el caso que dice
representar, en ningún sentido -- lo correcto es marcarla como no fiable,
no inventar una respuesta en cualquier dirección.

## Recomendación

- Los 3 casos pendientes (y su naturaleza `-`/`incertidumbre` en el
  desglose de `docs/validation_report.md`) no deberían contar como fallos
  reales de calibración de WatchGate al leer el % de la suite.
- Antes de invertir esfuerzo en "enseñar" al RAG a reconocer estos
  patrones (p. ej. "sé más suspicaz de utilidades base64 aisladas"), hay
  que verificar primero si el caso que lo motiva contiene de verdad el
  payload -- ver el caso concreto documentado en
  `docs/evaluacion_ia/comparativa_rag_modelos.md` (hallazgo #4) sobre el
  riesgo de crear una superficie de falsos positivos con ejemplos de
  calibración mal fundamentados.
- Arreglo real pendiente para los 3 casos restantes, no trivial: recuperar
  el fichero correcto de cada ZIP (la contraseña estándar del dataset
  DataDog, `infected`, ya se conoce -- ver "Casos resueltos") y reconstruir
  la fixture con el payload auténtico, siguiendo el mismo procedimiento que
  `mflux-streamlit_6`. Cada `KNOWN_ISSUE.md` en el propio directorio del
  caso afectado apunta a este documento.
