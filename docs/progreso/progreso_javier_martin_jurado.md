# Registro de progreso - Javier Martín Jurado

**Responsable:** Javier Martín Jurado · **Actualizado:** 2026-08-07 · **Estado:** Línea 2 completa (reputación + semántica + RAG), suite de aceptación real al 95%, adaptador GitHub Action operativo, dashboard completo y endurecido en producción.

Este documento resume, en orden cronológico, todo lo que he hecho en WatchGate desde que arrancó el proyecto (27 de julio) hasta hoy. Pensado para leerse entero en 10-15 minutos.

---

## 1. Arranque del proyecto (27-29 julio)

Estructura inicial de carpetas, `pyproject.toml`, reestructuración según la spec de implementación (`docs/WatchGate_spec_implementacion_IA.md`), y primer `make test` en verde con Poetry. Es la base sobre la que se construyó todo lo demás.

## 2. Línea 2 completa: reputación, capa semántica y RAG (4 agosto)

El bloque más grande. Implementé de cero:

- **Capa de reputación** (`reputation_layer.py`): puntúa señales del autor (cuenta nueva, sin contribuciones previas, email no verificado, commit sin firmar en un repo que sí firma, clave de firma nunca vista) sin hacer ninguna llamada de red — toda la metadata llega ya resuelta desde el adaptador.
- **Capa semántica multi-proveedor** (`_semantic/`): el LLM que evalúa la intención real de un cambio, con soporte para Anthropic, Gemini o cualquier backend local compatible con OpenAI (Ollama, llama.cpp...) — cambiar de proveedor es una variable de entorno, no código.
- **Tools acotadas para el LLM** (`tools.py`): consultar un registro de paquetes, leer un fichero completo bajo demanda (`fetch_referenced_file`), y una integración opcional con VirusTotal para detectar blobs maliciosos ya conocidos escondidos en un fichero (el caso XZ Utils).
- **RAG dinámico** (`rag/`): más allá de lo que pedía la spec — un bucle de feedback humano incremental (un caso confirmado por revisión se indexa y realimenta el sistema) y deduplicación de fragmentos para no gastar tokens de más.
- Corpus inicial con casos reales verificados (XZ Utils, SolarWinds, Trojan Source, dependency confusion...) y técnicas MITRE ATT&CK.

Probado contra las APIs reales de Anthropic, Gemini y VirusTotal, no solo con mocks. 131 tests en verde.

## 3. Calibración del RAG (5 agosto)

Separé la colección de "casos confirmados por feedback humano" de la del corpus público en ChromaDB, para que un caso confirmado tenga siempre hueco en la recuperación y no compita con un corpus que sigue creciendo. Amplié el corpus de 12 a 23 casos reales (event-stream, colors.js/faker.js, polyfill.io, Codecov...) y corregí un sesgo real: el modelo inflaba la severidad de un caso solo por reconocer el *nombre* de una técnica conocida (Trojan Source), sin comprobar si el truco surtía efecto de verdad en el diff. La solución no fue un aviso genérico en el prompt (no cambió nada) sino explicar la regla técnica exacta en el propio documento del corpus — verificado contra Gemini real.

## 4. Tres bugs bloqueantes de integración (5 agosto)

Al integrar la capa semántica de verdad (no con mocks) contra el trabajo de otro compañero en `orchestrator.py`, encontré y arreglé:

- El orquestador instanciaba las capas sin argumentos, pero `SemanticLayer` necesita `llm_client`/`cost_control` en el constructor → `TypeError` garantizado. Solución: inyección opcional de "cómo construir cada capa" (`layer_factories`), sin que el orquestador tenga que conocer el nombre "semantic".
- La conexión SQLite de `cost_control.py` no era segura entre hilos, y el orquestador ejecuta las capas en paralelo → error reproducido en vivo. Añadido `Lock` + `check_same_thread=False`.
- La caché guardaba/leía `dict` planos pero la capa semántica espera/produce un objeto Pydantic (`SemanticOutput`) → habría fallado al cachear un resultado real.

Los tests existentes pasaban porque usaban capas falsas que ocultaban estos tres problemas — añadí un test de integración con las piezas reales para que no vuelva a pasar desapercibido.

## 5. Ampliación de RAG/few-shot y documentación (5 agosto)

Caso real del gusano npm "Shai-Hulud" (posterior al corte de entrenamiento de los modelos, así que solo el RAG puede aportar esa señal), 4 ejemplos few-shot nuevos de código real verificado, e informe comparativo de RAG con distintos modelos de Gemini. También revertí unos `try/except` demasiado permisivos que un merge había introducido y que silenciaban en falso cualquier bug real de embeddings, no solo el caso que había que cubrir.

## 6. Suite de aceptación real: 191 casos (6 agosto)

Construí una suite de validación con casos reales (paquetes npm/PyPI comprometidos confirmados, no inventados) muy por encima del mínimo de 10 que pedía la spec, más un generador de informe (`generate_validation_report.py`) que corre la suite completa contra la API real de Gemini y desglosa el resultado por clase y dificultad. Resultado a día de hoy: **182/191 (95%)** — 100% en benignos fáciles/medios, 97-100% en el resto de benignos, 85-90% en maliciosos. De paso arreglé un deadlock real en `retriever.py` que bloqueaba ejecutar la suite en paralelo.

## 7. Mejoras de detección: 90% → 95% (6 agosto)

Con la suite ya funcionando, medí una por una cuatro mejoras hasta subir el acierto global del 90% al 95% (y del 20% al 90% específicamente en los maliciosos más difíciles), sin perder precisión en benignos:

- Mostrar un extracto real alrededor de líneas sospechosas en ficheros truncados, en vez de un resumen ciego.
- Auto-consistencia: cuando el score cae cerca de un umbral, se pide una segunda opinión y se usa la más alta (ataca el rebote real entre llamadas de un LLM no determinista).
- Suelo mecánico: si hay contenido sin verificar y el LLM no pidió verlo entero pudiendo hacerlo, el score no puede quedarse bajo.
- En la agregación final: si la capa semántica es de alta confianza y categoría grave (backdoor, exfiltración...), el resultado combinado ya no puede quedar diluido por debajo del umbral rojo solo porque la reputación del autor esté limpia — calibrado contra un caso real de una cuenta de npm comprometida sin ninguna señal de reputación sospechosa (justo el objetivo del ataque).

## 8. Bug de presupuesto cero (6 agosto)

Revisando un commit de seguridad de otro compañero encontré que fijar `monthly_budget_tokens=0` (queriendo decir "no gastes nada") se trataba igual que "sin límite" — justo lo contrario de la intención. Corregido y con tests. También limpié un hack en `deps_layer.py` que hacía que el código de producción se comportara distinto si detectaba que estaba siendo testeado.

## 9. Adaptador de GitHub Action: cierra el círculo hasta el PR (6 agosto)

Hasta este punto, `watchgate analyze` calculaba un score perfecto y no lo publicaba en ningún sitio. Implementé:

- **`core/pipeline.py`** (nuevo): saqué de la CLI el *wiring* real del análisis completo a una función compartida (`run_full_analysis`), para que la CLI y la Action no dupliquen lógica.
- **`github_client.py`**: cliente REST real contra GitHub que resuelve reputación de verdad (antigüedad de cuenta, contribuciones previas, firma de commits...), publica el comentario y marca el *check run* como bloqueante si el resultado es rojo.
- Test de seguridad obligatorio: la API key nunca aparece en la salida capturada, aunque sí se usa de verdad.

Con esto WatchGate pasó de ser una demo local a una herramienta que llega de verdad a un PR.

## 10. Detección de inyección de prompt (6 agosto)

Cerré un hueco de seguridad real: antes de esto, la única defensa contra que un PR intentara manipular al LLM con instrucciones falsas incrustadas en el diff (`"ignora las instrucciones anteriores"`, mensajes de sistema falsos, JSON de respuesta falsificado...) era el propio criterio del modelo. Añadí una detección mecánica de 9 patrones (`find_prompt_injection_attempts`) que, si encuentra un intento, fuerza el score a 100 pase lo que pase — el intento en sí ya es evidencia de ataque — más delimitadores explícitos en el prompt que marcan todo el contenido del diff como dato no confiable, nunca instrucciones.

## 11. Dashboard completo: backend y frontend (6 agosto)

Implementé la spec §13 de punta a punta:

- **Backend FastAPI**: cuatro vías de login (dev, usuario/contraseña, OAuth GitHub, OIDC genérico) que confluyen en la misma cookie de sesión; tres roles por repositorio; histórico de análisis con feedback humano; configuración de pesos/umbrales por repo y global; ajustes de LLM (con API key siempre enmascarada) y de UI; métricas de organización con tendencia y desglose por repo.
- **Frontend React 19 + Vite + TypeScript** con shadcn/ui, tema claro/oscuro, i18n en español y gráficas con recharts.

## 12. Endurecer el arranque del dashboard en producción (6 agosto)

El dashboard arrancaba en modo inseguro por defecto sin avisar: si alguien lo desplegaba sin fijar explícitamente las variables de entorno, seguía firmando cookies de sesión con un secreto público en el repo — cualquiera podría forjarse una sesión de administrador. Añadí una comprobación que **bloquea el arranque** en cuanto el operador declara "esto es un despliegue real" (`DEV_MODE=0`) si el secreto o el token de ingesta siguen en su valor por defecto.

## 13. Conectar la Action con el dashboard (6 agosto)

La Action publicaba el comentario en el PR pero nunca guardaba nada en el dashboard — quedó pendiente explícitamente en el punto 9. Lo cerré: la Action ahora envía cada resultado al dashboard por HTTP, de forma opcional (si no se configura, no pasa nada) y resiliente (si el dashboard está caído, el análisis no se pierde, solo se avisa por log). El endpoint de recepción, que ya existía pero estaba sin autenticar, ahora exige un token compartido.

## 14. Soporte Postgres real (6 agosto)

Antes de esto, "migrar a Postgres" era solo un comentario en el código. Construí un envoltorio que hace que las ~40 funciones de acceso a datos del dashboard funcionen igual contra SQLite o contra Postgres sin apenas tocarlas, y lo **validé contra un Postgres real** (no solo en teoría). En el proceso aparecieron y arreglé tres incompatibilidades reales que solo un motor con tipado estricto revela (fechas que vuelven como objeto en vez de texto, columnas booleanas que no aceptan enteros y viceversa, falta de un equivalente a `lastrowid`).

## 15. Otros

Memoria formal del proyecto (`docs/memoria_WatchGate.md`), presentación de kickoff en LaTeX/Beamer, corrección de un `poetry.lock` desincronizado que impedía instalar el proyecto en limpio, y un par de scripts de desarrollo para probar la Línea 2 y comparar resultados con/sin RAG.

---

## 16. Separación de la capa de vulnerabilidades y reporte con las 5 capas reales (7 agosto)

Separé `vulnerabilities_layer.py` (CVEs conocidas vía OSV.dev) de `deps_layer.py` (que se queda solo con señales de ataque a la cadena de suministro: typosquatting, scripts de instalación sospechosos, instalación directa por URL/Git), a petición explícita de poder desactivar una sin la otra -- una CVE conocida en una versión desactualizada no es evidencia de que *este* PR sea un ataque. De paso, hasta ahora `static_layer.py` estaba implementada y testeada pero nunca se importaba en `watchgate/core/layers/__init__.py`, así que `LAYER_REGISTRY["static"]` no existía en ninguna ejecución real (CLI/Action) pese a tener peso 0.25 por defecto -- corregido.

Con las 5 capas ya registradas de verdad, regeneré `docs/validation_report.md` contra la API real de Gemini: **168/193 (87%)** en la primera pasada, frente al 95% anterior que solo pesaba reputación+semántica. La caída no era un bug de este cambio sino dos cosas concretas, ambas ya cerradas:

- **12 casos con `ERROR`**: a varios `tests/cases/malreal_*` recientes les faltaba el directorio `after/` -- solo tenían `source.json` apuntando a un zip del dataset de DataDog sin materializar. Descargué y descifré (password `infected`, mismo esquema que el resto de la suite) los 12 zips, identifiqué el fichero realmente inyectado en cada uno -- 5 comparten el mismo dropper `setup_bun.js` de una campaña npm masiva vía `bun.sh/install`, 2 son exfiltradores directos (`index.js` con lectura de `/etc/passwd` a un colector Burp), 2 son scripts de auto-republicación (`auto.js`), y los 3 de PyPI son inyecciones escondidas en ficheros legítimos (`__init__.py` de durabletask descarga un segundo payload; `_client.py` de telnyx tiene esteganografía en un `.wav` con exfiltración RSA por doble capa Windows/Linux) -- y los añadí a `after/`.
- **Regresión real en `malicious hard` (36%) y `malicious medium` (43%)**: con solo reputación (0.15) + semántica (0.40) renormalizados, la capa semántica pesaba ~73% del score. Con las 5 capas activas pesa 40% nominal, y el suelo que protege una detección semántica de alta confianza (`aggregator.py::_apply_high_confidence_semantic_floor`) no cubría `RiskCategory.OFUSCACION` -- justo la categoría que fuerza `_apply_prompt_injection_floor` a 100 de forma determinista. Añadida `OFUSCACION` a las categorías graves del suelo, con test de regresión (`test_high_confidence_obfuscation_semantic_floors_score_to_red`) verificado contra los casos reales `prompt_injection_fake_approval`/`prompt_injection_hides_real_payload`.

Con ambos arreglos, la regeneración final da **180/193 (93%)**, 0 errores de ejecución, `malicious hard` 72% y `malicious medium` 86% (frente al 36%/43% de la primera pasada). Los 13 casos que aún divergen son en su mayoría el mismo patrón de siempre: la LLM se deja engañar por código malicioso que imita muy bien a código legítimo (typo real, no de este cambio) -- eso es trabajo de RAG/prompt, no de agregación.

Fusioné además `origin/main` (trabajo de Pablo: clasificación `ThreatNature`/`threat_summary`, sincronización de reglas Semgrep/YARA, CLI con Rich/SARIF/stdin) -- único conflicto real en `deps_layer.py`, porque su rama todavía tenía la consulta a OSV inline (de antes de esta separación). Resuelto a favor de la arquitectura separada; sus cambios de `ThreatNature` en `aggregator.py`/`models.py`/formatters se fusionaron limpios.

## 17. Revisión de seguridad multi-agente de todo lo fusionado de Pablo, y 25 fixes reales (8 agosto)

Tras la fusión del punto 16, lancé una revisión de seguridad sistemática (5 agentes en paralelo, uno por bloque: sync de reglas, Fases 1-4 del plan SaaS multi-tenant, Engine API + Postgres + gestión de keys, CLI moderna + `ThreatNature`) sobre todo el trabajo de Pablo que nunca se había auditado con este nivel de detalle. Cada hallazgo lo verifiqué yo mismo leyendo o reproduciendo el código real antes de tocarlo -- no me fié de lo que reportaba cada agente a ciegas. Arreglé 25 hallazgos reales en total, todos con test de regresión:

**Críticos (bloqueaban producción o eran RCE/bypass de autenticación):**
- Inyección de comandos en CI (`sync-rules.yml`/`reconcile-rules.yml`): `${{ github.event.client_payload.* }}` interpolado sin escapar dentro de `run:` bash -- un repo de reglas comprometido podía ejecutar comandos arbitrarios en un runner con `contents: write`.
- Path traversal en `sync_rules.py`: nombres de idioma/vendor del manifest sin validar, podían escribir fuera de `rules/` en el checkout.
- `config_override` en los endpoints de agente de IA (`/precheck`, `/analyze`, `/verify-fix`) permitía a un cliente HTTP neutralizar `thresholds`/`weights`/`block_on_red` -- el mismo agente que genera un PR malicioso podía autoaprobarlo.
- `init_db()` sin migración real: desplegar contra cualquier BD con datos previos rompía todo. Lo confirmé de verdad contra mi propio `.watchgate/app.db` local (quedó bloqueado hasta que lo até y recreé).
- **`_apply_malicious_and_uncertain_policy`/`shortcircuit.py` (encontrado en la segunda pasada, no en la primera)**: el `or risk_score >= thresholds["red"]` trataba un risk_score alto como si fuera lo mismo que alta confianza. `deps_layer.py` nunca rellena `confidence` (siempre `None`) y puntúa 75-80 para patrones habituales y a menudo legítimos (dependencia pinneada a una URL de git, script postinstall con `chmod +x`) -- con la config **por defecto**, cualquier hallazgo así forzaba el combinado a 100/ROJO pese a que la media ponderada real diera ~10/100. Reproducido con un caso concreto (pinnear `left-pad` a un commit de git). El único test que cubría esta ruta fijaba `confidence=ALTA` a mano, un valor que `deps_layer.py` nunca produce en la práctica -- el verde de CI no probaba nada del caso real. Esto también explica (parcialmente) los "falsos positivos" que anoté en el punto 16 como pendientes de revisar con Pablo -- aunque el caso concreto que motivó esa nota (`real_pallets_jinja_2105`) resultó ser la capa semántica equivocándose con confianza real, no este bug.
- Login OAuth de GitHub del Dashboard sin protección CSRF (`state`): un atacante podía capturar su propio `code` e inducir a la víctima a completar el callback, dejando su sesión vinculada a la identidad GitHub del atacante.

**Altos:**
- `record_token_usage` no atómico -> UPSERT atómico (verificado con 20 hilos concurrentes, 0 pérdidas); TOCTOU en `analyze_with_quota` cerrado con reserva atómica antes de llamar al LLM.
- Verificación de firma de webhook obligatoria en GitHub/GitLab/Bitbucket (antes: sin secreto configurado, se aceptaba cualquier payload).
- `pre_receive` ya no traga excepciones de `git diff` (fail-closed real) y el timeout se aplica de verdad vía `SIGALRM` (antes, un análisis colgado bloqueaba `git push` indefinidamente).
- Token de acceso de GitHub embebido en la cookie de sesión del Dashboard: el JWT está firmado pero no cifrado, así que cualquiera que lea el valor de la cookie (fuera de la red, ej. un HAR compartido) puede decodificarlo en base64 sin el secreto y obtener un token vivo con scope `repo,read:org`. **No lo he arreglado** -- necesita una decisión de diseño (cifrar el JWT con JWE, o mover a un almacén de sesión en servidor) que no me correspondía tomar sin hablarlo.

**Medios:**
- `$GITHUB_OUTPUT` con delimitador multilínea seguro; symlinks rechazados en hash/copia de reglas de `sync_rules.py`.
- `default-org` del Dashboard ahora es una Organización real y persistida (una por usuario, o el fallback compartido persistido de verdad) -- antes se fabricaba en memoria y nunca existía de verdad, así que cuota/gobernanza se saltaban en silencio.
- `scopes` de API key comprobados de verdad (`require_scope`); `create_user` ya no reasigna `org_id` de un usuario existente en silencio; `PolicyService` valida rangos y no tumba el análisis de una org con un `policy_json` malformado.
- Mapeo de permisos de GitHub (`_map_github_permission`) invertido de "conceder por defecto" a "denegar por defecto" -- un valor no reconocido (incluido `"none"`) ya no concedía `revisor`.
- `WATCHGATE_DASHBOARD_SECURE_COOKIE` y un secreto de sesión demasiado corto ahora bloquean el arranque en producción, igual que ya hacía el secreto por defecto.
- Canal lateral de tiempo en el login por contraseña (usuario inexistente respondía instantáneo, uno existente tardaba un PBKDF2 de 120k iteraciones) -- permitía enumerar logins válidos.
- Escapado incompleto en las anotaciones de GitHub Actions (`github.py`): un `file_path` con `:`/`,` podía inyectar propiedades falsas o un `::error::` completo en la anotación.

**Bajos:** fallo al escribir `--output` de la CLI no afectaba el exit code (ahora exit 3); keyword matching de `_infer_threat_nature_from_semgrep` sin límite de palabra (`"c2"` podía matchear por substring accidental).

Cobertura de test de Postgres sigue sin ser end-to-end automática (mismo pendiente del punto 14) -- eso es infraestructura de CI, no algo que se arregle en el propio código.

Verificación funcional real, no solo tests: arranqué el Engine API y el Dashboard de verdad (`TestClient` con lifespan completo) y confirmé que levantan limpios; corrí la CLI contra un diff real de este propio repo; invoqué el hook `pre-receive` como proceso real vía stdin. De paso, el nuevo chequeo estricto de `init_db()` destapó que `tests/integration/test_dashboard_roles.py` no aislaba su base de datos (tocaba el `.watchgate/app.db` real compartido, no un fixture) -- lo arreglé aplicando el mismo patrón que ya usaba `test_dashboard_api_keys.py`.

## 18. Cierre de los tres pendientes del punto 17 (8 agosto)

Los tres hallazgos que dejé documentados sin tocar por necesitar una decisión de diseño -- la tomé yo, explicada aquí para que se pueda revisar:

- **Token de GitHub sin cifrar en la cookie de sesión**: `create_session_token`/`decode_session_token` ahora hacen un JWT anidado -- se firma igual que antes (integridad/expiración) y ENCIMA se cifra con AES-256-GCM (`python-jose` ya era dependencia del proyecto, incluye `jose.jwe`). La clave de cifrado se deriva por SHA-256 del mismo `WATCHGATE_DASHBOARD_SECRET` (con un prefijo distinto al de firma, para no reusar literalmente los mismos bytes) -- una sola variable de entorno que gestionar, no hace falta añadir ninguna nueva. Descarté mover la sesión a un almacén en servidor por ser un cambio de arquitectura mucho mayor para el mismo problema.
- **Sin rate limiting en el login**: limitador en memoria de proceso, por login normalizado (no por IP), 5 intentos fallidos por 5 minutos, se resetea en un login correcto. Documentado explícitamente como limitación de un solo proceso -- con varias réplicas detrás de un balanceador haría falta un almacén compartido (Redis u otro), que no era proporcionado añadir para un proyecto que hoy corre en un único proceso.
- **RAG distribuido sin aislamiento por tenant**: `add_confirmed_case`/`retrieve_relevant_context` ahora aceptan `org_id` opcional; el feedback humano se guarda con `org_id` en la metadata de ChromaDB y se filtra con `where={"org_id": ...}` al consultar -- el corpus público (`attack_patterns`) sigue sin filtrar nunca, es intencionalmente compartido. `analyze_with_quota` (`service/quota.py`) inyecta `org_id` en el `metadata` que le llega a las capas, así que `SemanticLayer` ya lo lee solo sin que cada caller tenga que montarlo a mano.

Los tres con test de regresión (incluida una prueba de aislamiento cruzado real: dos orgs, cada una con su caso de feedback, confirmando que ninguna ve el caso de la otra). 445 tests en verde tras esto.

## 19. CI que no existía, y repo lint-limpio (8 agosto)

El proyecto tenía `make lint` (ruff + mypy + import-linter) y tests, pero ningún workflow de GitHub Actions los corría nunca -- un PR con la suite en rojo o con violaciones de arquitectura se podía fusionar sin que nada lo señalase. Añadí `.github/workflows/ci.yml` con dos jobs: `backend` (poetry install cacheado, `ruff check`/`ruff format --check`/`mypy`/`lint-imports`, `pytest --cov`) y `frontend` (`npm ci && npm run build`), en `push` a `main` y en cada PR.

Correr `ruff check .` de verdad por primera vez destapó 888 errores -- casi todos en `rules/` (fixtures Semgrep/YARA de terceros, vendorizadas, no son Python real del proyecto) que nunca se habían excluido del linter. Añadí `rules` y `scratchpad` a `extend-exclude` en `pyproject.toml`; lo que quedó tras eso fueron 42 ficheros con diferencias mecánicas de formato (`ruff format .`) y un único cambio real: `isinstance(v, (int, float))` -> `isinstance(v, int | float)` en `policy.py` (sintaxis moderna, `ruff` lo marca como upgrade automático). Cero cambios de comportamiento.

## 20. Contenedores Docker + Compose con Postgres real, y un bug de arquitectura que solo salió al desplegar de verdad (8 agosto)

Con CI cubriendo tests y lint, lo que le faltaba al repo para ser desplegable de verdad eran imágenes. Añadí `docker/engine-api.Dockerfile` y `docker/dashboard-backend.Dockerfile` (build multi-stage: `python:3.11-slim` builder con `poetry install`, runtime sin toolchain de compilación, usuario no-root, healthcheck contra `/health`), `watchgate/dashboard/frontend/Dockerfile` (`node:20-slim` build -> `nginx:1.27-alpine` sirviendo el estático, con `envsubst` de nginx para inyectar `BACKEND_ORIGIN` en el proxy de `/api/*` sin hornear la URL del backend en la imagen) y `docker-compose.yml` orquestando los 4 servicios (Postgres incluido).

No me fié de que "el Dockerfile compila" significase "el contenedor funciona" -- construí y arranqué cada imagen de verdad, y eso encontró dos bugs reales que una revisión de código no hubiera visto:

- **`ImportError: Bad git executable`** en el Engine API al arrancar: GitPython (dependencia transitiva, la usa `diffparser`) necesita el binario `git` en tiempo de ejecución, no solo durante el build -- lo tenía instalado solo en la etapa `builder`. Añadido a la etapa `runtime` de ambos Dockerfiles Python.
- **`sqlite3.OperationalError: unable to open database file`**: el usuario no-root del contenedor no tenía permisos de escritura en `.watchgate/` (donde cae el SQLite/cache por defecto si no se configura Postgres). Añadido `mkdir + chown` antes de `USER watchgate`.

El bug más serio lo encontré probando el `docker-compose.yml` completo contra un Postgres real: **`watchgate/dashboard/backend/db.py`** (esquema propio del Dashboard, SQL crudo) y **`watchgate/db/models.py::PRScore`** (esquema SQLModel de la Fase 1, compartido con el Engine API) definen ambos una tabla llamada `pr_scores`, con columnas completamente distintas. Mi primer `docker-compose.yml` apuntaba `WATCHGATE_DATABASE_URL` y `WATCHGATE_DASHBOARD_DATABASE_URL` a la misma base de datos de Postgres -- el Dashboard backend crea primero la tabla `pr_scores` del esquema SQLModel (vía `init_api_keys_db()`), y cuando el esquema propio del Dashboard intenta crear la suya con ese nombre, Postgres ve una tabla ya existente con columnas que no coinciden. Lo detectó en el momento mi propio `_check_schema_matches_models()` (añadido en el punto 17) con un `SchemaOutOfDateError` listando columnas "faltantes" que en realidad pertenecían al otro esquema -- exactamente el tipo de fallo silencioso que ese chequeo se diseñó para atrapar, solo que esta vez el "esquema desactualizado" real era "esquema equivocado".

Arreglado sin tocar código de ninguno de los dos esquemas: `docker/postgres-init/01-create-dashboard-db.sql` (montado en `/docker-entrypoint-initdb.d/` del contenedor de Postgres, se ejecuta una sola vez al crear el volumen) provisiona una segunda base de datos, `watchgate_dashboard`, separada de `watchgate`. Cada esquema vive en su propia base de datos dentro del mismo servidor Postgres.

Verificación real, no solo "debería funcionar": recreé el escenario con contenedores manuales (Postgres + init script + Dashboard backend apuntando a las dos bases separadas) y confirmé que el `SchemaOutOfDateError` desaparece y ambas tablas `pr_scores` se crean con sus columnas correctas (columna por columna, con `\d pr_scores` en cada base). Después corrí `docker compose up --build` de principio a fin: los 4 servicios arrancan `healthy`, los tres endpoints HTTP (`GET /health` del Engine API, `GET /api/health` del Dashboard backend, `GET /` del frontend) responden 200, y un login de desarrollo a través del proxy nginx del frontend (`POST /api/auth/dev-login` -> `GET /api/auth/me` con la cookie de sesión) confirma que la cadena completa nginx -> Dashboard backend -> Postgres funciona de extremo a extremo, no solo cada pieza por separado. 445 tests siguen en verde tras todo esto.

Documentado en `docs/despliegue.md` (los 4 servicios, cómo levantar el stack, el porqué de las dos bases de datos, checklist de producción, limitaciones honestas) y `README.md` (sección "Despliegue" enlazando ahí). Añadidos `make docker-up`/`make docker-down`.

## Estado global

**445 tests** en verde (`python -m pytest`, suite completa salvo la de aceptación real marcada `integration`), ahora corridos en CI (`.github/workflows/ci.yml`) en cada push/PR, no solo en local. **180/193 (93%)** en la suite de aceptación real con las 5 capas reales (sin cambios desde el punto 16 -- los fixes de los puntos 17/18 no se han vuelto a correr contra esa suite todavía). El stack completo (Engine API + Dashboard backend/frontend + Postgres real, dos bases de datos separadas) se levanta con `docker compose up --build` y está verificado de extremo a extremo (ver punto 20). Todo lo listado arriba está en producción salvo estos matices honestos:

- Postgres está validado de extremo a extremo vía `docker compose up`, pero no hay un Postgres provisionado en el propio pipeline de CI (`ci.yml` corre los tests contra SQLite, más rápido y sin infraestructura extra en cada push).
- La detección de inyección de prompt es un heurístico de texto (regex); un atacante que ofusque el contenido (Unicode, base64) podría evadirlo.
- El rate limiting del login es en memoria de proceso -- no protege entre réplicas si algún día el dashboard se despliega con más de un worker.
- Sin migraciones automáticas de esquema (Alembic o equivalente) -- `init_db()` falla alto y claro si detecta columnas que faltan, pero aplicar el `ALTER TABLE` sigue siendo manual.
- Engine API y Dashboard backend empaquetan las mismas dependencias pesadas (torch/semgrep/chromadb) en su imagen Docker aunque el Dashboard backend no las use en runtime -- no se ha separado el empaquetado por extras de Poetry todavía.

## Pendiente

- Provisionar Postgres en el CI para cobertura automática de extremo a extremo (hoy solo vía `docker compose up` manual).
- Regenerar `docs/validation_report.md` contra la API real para reflejar los fixes de los puntos 17/18 (especialmente el de `_apply_malicious_and_uncertain_policy`, que debería mejorar `malicious medium/hard`).
- Si el dashboard pasa alguna vez a desplegarse con varias réplicas: mover el rate limiting de login a un almacén compartido.
- Evaluar Alembic (o equivalente) si el esquema empieza a cambiar con frecuencia -- hoy el chequeo estricto de arranque es suficiente para un proyecto de este tamaño.
- Publicar el paquete en PyPI (fuera de alcance por decisión explícita).
- Ampliar la detección de inyección de prompt si se observan variantes ofuscadas en producción.
