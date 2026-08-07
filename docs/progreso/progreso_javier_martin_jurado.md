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

Con las 5 capas ya registradas de verdad, regeneré `docs/validation_report.md` contra la API real de Gemini: **168/193 (87%)**, frente al 95% anterior que solo pesaba reputación+semántica. La caída es real y viene de dos sitios distintos, no de un bug de este cambio:

- **12 casos con `ERROR`** (no cuentan como fallo de detección): a varios `tests/cases/malreal_*` recientes les falta el directorio `after/` -- solo tienen `source.json` apuntando a un zip del dataset de DataDog que nunca se llegó a descargar/materializar. Pendiente aparte, no relacionado con las capas.
- **Regresión real en `malicious hard` (36%) y `malicious medium` (43%)**: con solo reputación (0.15) + semántica (0.40) renormalizados, la capa semántica pesaba ~73% del score. Con las 5 capas activas pesa 40% nominal, y `static`/`dependencies`/`vulnerabilities` puntúan 0 en ataques que son puramente lógicos (paquete npm comprometido con código que parece código normal, sin typosquatting/script/CVE) -- diluyen exactamente los casos donde la capa semántica es la única señal real. `benign` se mantiene en 100% en las tres dificultades.

## Estado global

**266/266 tests** unitarios e integración en verde. **168/193 (87%)** en la suite de aceptación real con las 5 capas reales (12 de las divergencias son fixtures incompletas, no fallos de detección -- ver §16). Todo lo listado arriba está en producción salvo estos matices honestos:

- El soporte Postgres está validado a mano contra una instancia real, pero no hay un Postgres provisionado en el CI del proyecto, así que no hay un test automático de extremo a extremo en cada push.
- La detección de inyección de prompt es un heurístico de texto (regex); un atacante que ofusque el contenido (Unicode, base64) podría evadirlo.
- Con las 5 capas activas, la detección de ataques puramente semánticos en `malicious hard/medium` baja a 36-43% (ver §16) -- probablemente hace falta un suelo o ponderación distinta cuando la capa semántica es de alta confianza y las demás no aportan señal, no solo diluir por peso nominal.

## Pendiente

- Provisionar Postgres en el CI para cobertura automática de extremo a extremo.
- Rematerializar los `tests/cases/malreal_*` a los que les falta `after/` (12 casos, ver §16) desde el dataset de DataDog.
- Revisar la fórmula de agregación para que `static`/`dependencies`/`vulnerabilities` en 0 no diluyan una capa semántica de alta confianza (mismo principio que el "suelo" que ya existe para categorías graves, spec §7 punto 7).
- Publicar el paquete en PyPI (fuera de alcance por decisión explícita).
- Ampliar la detección de inyección de prompt si se observan variantes ofuscadas en producción.
