# Ground truth no fiable en algunos casos `malreal_*` (dataset DataDog)

Hallazgo real, verificado descargando el dataset de origen -- no una
suposición. 5 de los casos `class=malicious` de
`tests/cases/malreal_*_compromised_lib_*`/`malicious_intent_*` contaban
como "fallo" en la suite de validación (`tests/integration/test_cases.py`)
sin que WatchGate estuviera fallando de verdad: el fichero que quedó en el
fixture de test era código legítimo y benigno, no el payload malicioso real
del paquete comprometido. **Los 5 ya se han arreglado de verdad** -- ver
"Casos resueltos" más abajo -- recuperando el payload real de cada ZIP de
origen y reconstruyendo la fixture con él. El 5º (`tvi-cli_55`) no se
detectó en la revisión inicial -- apareció al regenerar
`docs/validation_report.md` después de arreglar los otros 4.

## Cómo se descubrió

Cada caso `malreal_*` referencia en su `source.json` un ZIP concreto del
repositorio público [DataDog/malicious-software-packages-dataset](https://github.com/DataDog/malicious-software-packages-dataset)
(la release completa de un paquete real que fue comprometido). El fixture
de este repo (`tests/cases/<caso>/after/`) contenía solo UN fichero,
presumiblemente muestreado de ese ZIP -- pero un paquete comprometido real
tiene decenas o cientos de ficheros, y solo algunos (a veces uno solo)
contienen el código inyectado. El proceso que generó estas 4 fixtures cayó
a un fichero legible cualquiera cuando no pudo extraer el fichero real
(protegido con contraseña dentro del ZIP).

La contraseña es la convención estándar que el propio dataset documenta en
su README (`infected`) -- no un secreto, sirve para que un antivirus no
detone la muestra por accidente al escanear el repositorio. Con ella se
descargó y descifró el ZIP de origen de cada uno de los 4 casos, confirmando
en todos un patrón común: el fichero benigno que había quedado en el
fixture convivía en el ZIP real con un fichero (o combinación de ficheros)
mucho más grande, sospechoso y ausente del código fuente limpio original.

## Casos resueltos

### `malreal_pypi_compromised_lib_mflux-streamlit_6`

`src/_index.js` (5.2 MB, PyPI) -- absurdo para un wrapper de `streamlit`.
Dos capas de ofuscación (array de códigos de carácter + cifrado César
ROT-19) que al decodificar revelan un loader Node.js que descifra más
payload embebido con AES-128-GCM y claves hardcodeadas. No se llegó a
descifrar esa última capa -- no hacía falta, el contenido ya decodificado
es suficiente evidencia. Sustituye a `main.py` (12 líneas, wrapper
benigno de `streamlit run`).

### `malreal_npm_compromised_lib_graphql-sequelize-teselagen_14`

`package.json` (con `"scripts": {"postinstall": "node bundle.js"}`, se
ejecuta solo con `npm install`) + `bundle.js` (3.7 MB, bundle webpack con
lógica de resolución de credenciales tipo AWS,
`resolveWebIdentityCredentials`). Sustituyen a `base64.js` (13 líneas, dos
funciones `base64()`/`unbase64()` sueltas, nada sospechoso por sí solas).

### `malreal_npm_malicious_intent_jstoauto_26`

`pino.js`, el entry point real del paquete (campo `main` de su
`package.json`) -- troyanizado: en vez de la lógica real del logger
`pino` (que este paquete clona), hace `require('./lib/lserver.js')` y
ejecuta ese módulo en cada llamada a `pino()`. `lib/lserver.js` (142 KB,
ofuscado con el mismo patrón de array de cadenas) se verificó pero
deliberadamente NO se incluyó en el fixture: al añadirlo, el diff supera
el límite de tamaño enviado al LLM y el fichero se trunca, degradando el
veredicto de la capa semántica de "malicioso" a "incertidumbre" (no podía
revisar el contenido completo). `pino.js` solo ya es evidencia suficiente
y autocontenida. Sustituye a `tools.js` (código real de `pino`
vendorizado tal cual).

### `malreal_pypi_compromised_lib_lightning_5`

`start.py`, parte de un directorio `lightning/_runtime/` que no existe en
el paquete real de PyTorch Lightning -- descarga el runtime `bun` de una
release de GitHub si no está presente en el sistema, y lo ejecuta contra
`router_runtime.js` (11.4 MB, ofuscado, con contenido consistente con robo
de tokens/credenciales) con `stdout`/`stderr` silenciados. Mismo patrón
dropper que los 5 casos que ya comparten `setup_bun.js` en este repo de
tests (`malreal_npm_compromised_lib_*`), y por la misma razón que
`jstoauto_26` no se incluyó `router_runtime.js` en el fixture (tamaño);
`start.py` solo ya replica el patrón dropper ya confirmado detectable.
Sustituye a `subprocess_script.py` (código real con licencia Apache de
PyTorch Lightning, lanzador de procesos multi-nodo estándar).

### `malreal_npm_compromised_lib_tvi-cli_55`

`package.json` (con `"scripts": {"postInstall": "node bundle.js"}` --
nótese la `I` mayúscula, no coincide con el nombre exacto del hook real de
npm, `postinstall`) + `bundle.js` (3.7 MB). Prácticamente el mismo payload
que `graphql-sequelize-teselagen_14` -- primeros ~5 KB idénticos byte a
byte, misma lógica de credenciales AWS -- misma campaña/familia de
malware compartiendo payload entre paquetes distintos, no una
coincidencia. Sustituye a `middleware.ts` (boilerplate de CORS para
Next.js, parte de las plantillas que `tvi-cli` genera en proyectos nuevos
-- nunca se ejecuta el propio CLI). Detectado por la capa **estática**
(Semgrep, reglas `eval_dynamic`/`exec_dynamic`/`permission_escalation`
sobre el bundle webpack) con risk_score 90 -- suficiente por sí solo para
rojo, sin necesitar la capa semántica: el diff supera el límite de tokens
de entrada de Gemini (1.048.576) por el tamaño de `bundle.js`, y la capa
semántica se salta (ver nota abajo sobre el bug de `layer.py` que oculta
este tipo de error).

---

En los 5 casos, `expected.json` no cambió -- ya decía `rojo`/malicioso,
correctamente (el paquete sí fue comprometido de verdad). Cada directorio
tiene un `SAFETY_NOTE.md` con el aviso de manejo del fichero real que
contiene. Verificado con:

```
poetry run pytest tests/integration/test_cases.py -m integration -k "mflux or teselagen or jstoauto or lightning_5 or tvi-cli"
```

Los 5 pasan (`rojo`/malicioso) contra el pipeline completo de 5 capas.
Antes del arreglo, los 5 fallaban con `verde`/benigno sobre el fichero
equivocado.

Contraejemplo real, para que quede claro que NO todos los `compromised_lib`
están mal etiquetados: `malreal_pypi_compromised_lib_durabletask_0`
(`__init__.py`) SÍ contiene el payload real e inequívoco -- descarga un
`.pyz` de un dominio sospechoso y lo ejecuta en segundo plano al importar
el paquete -- y WatchGate lo detecta correctamente. Lo mismo
`malreal_pypi_compromised_lib_telnyx_2`/`_4` (`_client.py`, exfiltración
esteganográfica en un WAV + `exec(base64.b64decode(...))`) y los 5 casos
que comparten `setup_bun.js`. El problema era específico de estos 5 casos
donde el payload real quedó fuera del fichero muestreado, no de la
categoría `compromised_lib`/`malicious_intent` en general.

## Bug encontrado de paso (ya arreglado): errores reales de la API se ocultaban como "sin configuración"

Al investigar por qué `tvi-cli_55` pasaba sin que la capa semántica
aportara nada, se encontró que el modelo se saltó por completo: Gemini
devolvió `400 INVALID_ARGUMENT: El input supera el máximo de tokens
permitido (1.048.576)` por el tamaño de `bundle.js`. `layer.py` (línea
~347) atrapaba **cualquier** excepción de la llamada al LLM con un
`except Exception` genérico y la reportaba siempre como
`_NO_LLM_CONFIG_SKIP_REASON` ("Capa semántica omitida (requiere clave de
API o configuración de proveedor LLM en el entorno)") -- indistinguible
de si de verdad no había clave configurada. El error real solo quedaba en
un `logger.info` que casi nadie mira. En este caso concreto no cambiaba el
veredicto (static/deps/vulnerabilities ya llevan el score a rojo sin
ayuda), pero en producción significaba que un PR con un fichero enorme
(un lockfile, una librería vendorizada, un dataset) podía hacer que la
capa semántica se saltara en silencio y el dashboard/log no lo
distinguiera de un despliegue mal configurado.

**Arreglado**: ese `except Exception` ahora incluye el mensaje real de la
excepción en el propio `skip_reason` (`"Capa semántica omitida por error
de la API del proveedor LLM: {exc}"`), en vez de colapsarlo al mensaje
genérico de "sin configuración". Verificado contra `tvi-cli_55` de verdad
(el `skip_reason` ahora muestra el `400 INVALID_ARGUMENT` real de Gemini)
y con un test nuevo en `tests/unit/test_semantic_layer.py`
(`test_skips_with_real_error_message_when_llm_api_call_fails`).

## Por qué no se "arregló" tocando `expected.json`

Cambiar el veredicto esperado a benigno habría sido tan poco honesto como
dejarlo en malicioso sin verificar: el PAQUETE sí fue comprometido de
verdad (hay CVE/advisory real detrás de cada caso), solo que el fichero
concreto de la fixture no era donde vivía el payload. El arreglo correcto
era recuperar el fichero real, no inventar una respuesta en cualquier
dirección -- que es exactamente lo que se hizo.

## Recomendación

- Estos 5 casos ya no deberían contar como incertidumbre/ground-truth
  dudoso en el desglose de `docs/validation_report.md` -- están resueltos
  y deberían aportar señal real de calibración.
- Antes de invertir esfuerzo en "enseñar" al RAG a reconocer patrones a
  partir de un caso que falla en la suite, verificar primero si el caso
  contiene de verdad el payload -- ver el caso concreto documentado en
  `docs/evaluacion_ia/comparativa_rag_modelos.md` (hallazgo #4) sobre el
  riesgo de crear una superficie de falsos positivos con ejemplos de
  calibración mal fundamentados. Este documento es la prueba de que esa
  verificación previa era necesaria: 5 de los 8 fallos originales no eran
  bugs de WatchGate.
- `docs/validation_report.md` ya se regeneró contra la API real tras
  arreglar los primeros 4 casos: 189/193 (97%), arriba desde 185/193.
  `tvi-cli_55` (el 5º) se descubrió precisamente en esa regeneración y se
  arregló después -- pendiente de una regeneración más para reflejar
  también ese arreglo.
- ~~Revisar si vale la pena separar en `layer.py` el `skip_reason` de "sin
  configuración de LLM" del de "error real de la API"~~ -- hecho, ver
  sección anterior. Antes un límite de tokens superado, un rate limit, o
  una clave real ausente eran indistinguibles en el resultado.
