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
- ~~Revisar si vale la pena separar en `layer.py` el `skip_reason` de "sin
  configuración de LLM" del de "error real de la API"~~ -- hecho, ver
  sección anterior. Antes un límite de tokens superado, un rate limit, o
  una clave real ausente eran indistinguibles en el resultado.

## Dos regeneraciones de `docs/validation_report.md`, dos números distintos (189 y 187 de 193)

Tras arreglar los 5 casos de ground truth, se regeneró el informe dos
veces (misma suite, mismo código, contra la API real ambas veces):
189/193 (97%) la primera, 187/193 (96%) la segunda, ~24h después. Los 5
casos arreglados en este documento **siguen arreglados** en las dos --
ninguno de los 5 aparece en los divergentes de ninguna de las dos tandas.
Lo que cambia es el conjunto de casos `real_*` (PRs benignos reales) que
disparan un falso positivo -- casi sin solape entre una tanda y otra
(`real_pallets_jinja_2098` falló en la primera y pasó en la segunda;
`real_pallets_flask_5492`/`real_pallets_jinja_2105`/`real_click_deprecate_isolated_fs`
fallaron solo en la segunda). Es la varianza de auto-consistencia
documentada en `_semantic/layer.py` operando sobre casos cerca de un
umbral -- confirmado también con `malreal_pypi_compromised_lib_lightning_5`
(uno de los 5 ya arreglados), que pasó en la primera tanda (rojo/70) y
salió amarillo/40 -- justo en el umbral -- en la segunda.

Dos casos SÍ se repiten en las tres tandas con resultado estable --
investigados a fondo, ver "Los dos casos persistentes, investigados" más
abajo. Ninguno de los dos resulta ser un bug real de WatchGate.

## Tercera regeneración, con `gemini-3.6-flash` (tras arreglar el SDK)

Cambiar el modelo por defecto de `gemini-2.5-flash` a `gemini-3.6-flash`
rompió primero por un problema de SDK, no del modelo (`google-genai`
0.8.0, congelado por un `<1` en `pyproject.toml`, no soporta
`thought_signature` -- campo nuevo que Gemini 3.x exige en las respuestas
de function-calling; cualquier caso que necesitara una tool fallaba con
400 y la capa semántica se saltaba entera). Arreglado subiendo el SDK a
2.17.0 (commit `a0a79a3`). Con el SDK ya arreglado: **188/193 (97%)**,
en línea con las dos tandas anteriores con `gemini-2.5-flash`.

De los 5 divergentes de esta tanda, `false_positive_candidate` y
`malreal_pypi_malicious_intent_mirrorbot_10` siguen ahí -- ya van 3/3
tandas, con dos modelos distintos, reforzando que son candidatos reales a
problema de calibración, no ruido de un modelo concreto.
`malreal_pypi_compromised_lib_lightning_5` (uno de los 5 ya arreglados)
también vuelve a divergir (verde/4) -- coherente con que sigue siendo un
caso borderline por naturaleza (el dropper `start.py` es sutil, sin el
payload `router_runtime.js` en el fixture por su tamaño), no una prueba de
que el arreglo esté mal.

## Los dos casos persistentes, investigados

Tras la 3ª tanda consecutiva fallando, se investigó cada uno leyendo el
fichero real del fixture (y, para `mirrorbot_10`, el ZIP de origen).
Ninguno de los dos resulta ser un bug real de detección de WatchGate --
cada uno revela un tipo de problema distinto a los 5 ya documentados
arriba.

### `false_positive_candidate`: puede que el modelo tenga razón y el test no

`tests/cases/false_positive_candidate/after/formulas.py`:

```python
_ALLOWED_NAMES = {n: getattr(math, n) for n in ('sqrt', 'sin', 'cos', 'floor', 'ceil')}

def evaluate_formula(expr, cell_values):
    namespace = dict(_ALLOWED_NAMES)
    namespace.update(cell_values)
    return eval(expr, {'__builtins__': {}}, namespace)
```

`eval(expr, {'__builtins__': {}}, namespace)` es la técnica clásica de
"sandbox de Python con builtins vacíos" que se sabe, desde hace años, que
NO aísla nada de verdad: cualquier objeto del namespace (aquí, las
funciones de `math`) expone `__globals__`, desde donde se recupera acceso
a los builtins reales (`sqrt.__globals__['__builtins__']`) y de ahí a
`exec`/`eval`/`__import__` sin restricción -- RCE real, técnica bien
documentada, no un caso rebuscado. El modelo lo sube a rojo(70) las 3
veces; `expected.json` (case `class: canonico`, diseñado a propósito para
esto) esperaba solo amarillo (min. 20).

**Arreglado**: `expected.json` se amplió para aceptar `["amarillo",
"rojo"]` (min. 20 sin cambios) -- mismo patrón ya usado en otros casos
ambiguos de la suite (p. ej. `mirrorbot_10`), no una corrección forzada a
verde ni una invención de una respuesta nueva. Rojo sigue contando como
detección válida de un problema real; el test ya no penaliza al modelo
por escalar una vulnerabilidad de RCE genuina más de lo que el fixture
anticipaba. Verificado con `pytest -m integration -k
false_positive_candidate`: pasa.

### `malreal_pypi_malicious_intent_mirrorbot_10`: no falta el payload, es un desajuste de categoría

A diferencia de los 5 casos de la sección anterior, aquí el fichero del
fixture (`direct_link_generator.py`, 809 líneas) SÍ coincide con el
fichero real del ZIP de origen (mismo tamaño, mismo contenido) -- no es un
caso de "fichero equivocado muestreado". Es código real y funcional de un
bot de Telegram (`mirrorbot`) que genera enlaces de descarga directa desde
servicios de alojamiento (mediafire, uptobox, 1fichier, terabox...),
usando `cloudscraper`/`lk21.Bypass` para esquivar captchas/protecciones
anti-bot de esos sitios. Revisado el fichero completo buscando
exfiltración, credenciales robadas o ejecución de comandos ocultos: nada
de eso -- las "cookies" que maneja (`XSRF-TOKEN`, `laravel_session`,
`PHPSESSID`) son credenciales propias del operador del bot para
autenticarse contra esos servicios, no robadas a terceros.

Hipótesis más probable: el dataset DataDog etiqueta `mirrorbot` como
`malicious_intent` por su **propósito** (facilita descargar/redistribuir
contenido desde servicios que no lo permiten, un problema de ToS/copyright
más que de seguridad), no porque el código contenga un payload de ataque a
la cadena de suministro. Ese criterio de "malicioso" no coincide con el
que usa WatchGate (backdoors, exfiltración, RCE, manipulación de
dependencias) -- WatchGate, correctamente dentro de su propio alcance, no
encuentra nada de eso aquí.

Antes de decidir qué hacer, se revisó también el resto del paquete (78
ficheros Python del ZIP completo, no solo el fichero del fixture): sin
IPs hardcodeadas, sin `eval`/`exec` sobre contenido decodificado, sin
`setup.py` con hooks de instalación, sin endpoints de exfiltración
conocidos. Nada.

**No arreglado, documentado como no-bug** (`KNOWN_ISSUE.md` en el
directorio del caso): a diferencia de `false_positive_candidate`, aquí no
hay una corrección obvia y unilateral que hacer -- ampliar a verde sería
inventar una respuesta tan poco fundamentada como dejarlo en rojo.
Confirmación adicional, sin inducirla: la propia justificación del modelo
en la última tanda dice, textualmente, *"El fichero
direct_link_generator.py implementa funciones legítimas para extraer
enlaces de descarga directa de múltiples servidores de almacenamiento,
sin incluir patrones de exfiltración, backdoors ni código malicioso"* --
la misma conclusión a la que se llegó aquí de forma independiente. El
caso sigue "fallando" mecánicamente en la suite (verde 11-39 según la
tanda, por debajo de min. 35), pero ya no cuenta como un hueco de
detección sin explicar.

### Lección general para el equipo

De los 8 fallos originales reportados en esta suite, ahora sabemos que:
5 eran ground truth con el fichero equivocado (arreglados), 1 es un
desajuste de categoría del dataset (no un bug), y 1 es un caso donde el
propio test podría estar mal calibrado, no el modelo. Solo entonces queda
lo que sí es varianza real del modelo cerca de umbrales (documentado
arriba). Antes de invertir esfuerzo en "arreglar" un fallo de esta suite
-- vía RAG, prompts, o cualquier otro mecanismo -- conviene primero leer
el fichero real del caso y preguntarse si el fallo es de WatchGate o del
propio dataset/test.

## Cuarta regeneración: 190/193 (98%), el mejor resultado hasta ahora

Tras arreglar `false_positive_candidate` y documentar `mirrorbot_10`, se
regeneró el informe una vez más: **190/193 (98%)**. `false_positive_candidate`
ya no divergía -- confirma que el arreglo de su `expected.json` se
sostiene contra la API real, no solo en la comprobación puntual. Quedan 3
divergentes: `mirrorbot_10` (esperado, documentado como no-bug),
`malreal_pypi_compromised_lib_lightning_5` (varianza de umbral ya
conocida, uno de los 5 casos de ground truth ya arreglados) y un caso
nuevo de ruido en `real_pydantic_pydantic_13577` (mismo patrón de falsos
positivos ocasionales en PRs benignos reales, documentado arriba).
