# Integración con el repo de reglas (Semgrep/YARA)

**Fecha:** 2026-08-07
**Estado:** implementado, desplegado y verificado en producción (versión activa `v0.0.2`).

## 1. Objetivo

`watch_gate` necesita las reglas de análisis estático (Semgrep) y de detección de malware (YARA) que mantiene el repo privado **`pablojimz/Repo-reglas-SEMGREP-y-YARA`**. Ese repo las versiona por release (`v0.0.1`, `v0.0.2`, ...) y, cuando publica una nueva, avisa a `watch_gate` mediante un evento `repository_dispatch` de tipo `rules-updated`.

Este documento describe la parte **consumidora** de ese flujo: cómo `watch_gate` recibe el aviso, descarga solo lo que cambió, **verifica su integridad por hash antes de activar nada**, y deja constancia de qué versión está activa — sin descargar ni ejecutar nunca una regla que no haya pasado esa verificación.

## 2. Piezas implementadas

| Fichero | Qué es |
|---|---|
| [`.github/workflows/sync-rules.yml`](../.github/workflows/sync-rules.yml) | Se dispara con el evento `repository_dispatch` real. Sincroniza solo el delta (`languages_changed` / `third_party_changed` del payload) + YARA completo siempre. |
| [`.github/workflows/reconcile-rules.yml`](../.github/workflows/reconcile-rules.yml) | Red de seguridad: cron diario (03:00 UTC) + disparo manual. Compara la versión activa contra la última Release publicada y, si difieren, reconcilia TODO. |
| [`scripts/sync_rules.py`](../scripts/sync_rules.py) | Lógica reutilizable por los dos workflows: checkout disperso con Git LFS, descarga del manifest vía Releases API, verificación de hash por clave, activación todo-o-nada, estado persistente. |
| [`scripts/rules_hash.py`](../scripts/rules_hash.py) | Hash SHA-256 determinista de una carpeta (mismo método que `build_release_manifest.py` del repo de reglas), aislado para poder testearlo sin red ni git. |
| [`rules/.rules-state.json`](../rules/.rules-state.json), [`rules/.rules-version`](../rules/.rules-version) | Estado activo: versión + hash verificado, acumulado por clave. |
| [`tests/unit/test_sync_rules.py`](../tests/unit/test_sync_rules.py), [`tests/unit/test_sync_rules_git_lfs.py`](../tests/unit/test_sync_rules_git_lfs.py) | 46 tests: lógica pura + Releases API mockeada, y mecánica real de git+LFS contra un repo local. |

## 3. Cómo funciona

```
Repo de reglas publica release vX.Y.Z
        │
        │  repository_dispatch "rules-updated"
        │  (payload = manifest.json: version, hashes por clave,
        │   languages_changed, third_party_changed)
        ▼
sync-rules.yml
        │
        ├─ 1. Descarga manifest.json como ASSET de la Release vX.Y.Z
        │      (Releases API, nunca la rama main -- ver §5.1)
        ├─ 2. Sparse-checkout disperso del repo de reglas, fijado al tag
        │      exacto, con Git LFS -- solo las carpetas que cambiaron
        │      + TODAS las categorías YARA (siempre completas)
        ├─ 3. Verifica el hash de CADA carpeta descargada contra el
        │      hash publicado en el manifest, de forma independiente
        ├─ 4a. Si TODAS coinciden → copia el contenido a rules/ de
        │       watch_gate, actualiza rules/.rules-state.json, comitea
        │       y hace push -- automático, sin intervención humana
        └─ 4b. Si alguna falla → no activa NADA (ni las que sí
                verificaron) y el workflow falla explícitamente,
                listando qué clave(s) fallaron
```

`reconcile-rules.yml` hace lo mismo pero disparado por reloj en vez de por evento, comparando primero (barato: solo el manifest) antes de decidir si hace falta la sincronización completa (cara: checkout + LFS + verificación).

## 4. Estructura de reglas y mapeo de rutas

| Repo de reglas | `watch_gate` (aquí) |
|---|---|
| `rules/semgrep/custom/<lenguaje>/` | `rules/semgrep/custom/<lenguaje>/` (igual) |
| `rules/semgrep/third-party/<vendor>/<carpeta>/` | `rules/semgrep/third-party/<vendor>/<carpeta>/` (igual) |
| `dist/yara_scored/<categoria>/` | `rules/yara/<categoria>/` (remapeado) |
| `manifest.json` (asset de Release) | `rules/manifest.json` (copia íntegra) |
| — | `rules/.rules-state.json`, `rules/.rules-version` (nuevo, estado activo) |

`rules/semgrep/config.yaml` (config de LiteLLM, sin relación con las reglas) se excluye siempre explícitamente — ver §5.3.

## 5. Decisiones de diseño y bugs reales resueltos

Este apartado documenta tanto las decisiones tomadas a priori como los tres fallos reales que aparecieron al desplegarlo contra el repo de reglas de verdad, y cómo se corrigieron — útil para justificar el diseño en la memoria del proyecto.

### 5.1 El manifest se lee de la Release, nunca de `main`

**Decisión inicial (incorrecta):** se asumió que `manifest.json` era un fichero commiteado en el árbol git del repo de reglas, leído vía la Contents API (`--ref main`).

**Fallo real:** `404 Not Found`. `manifest.json` no vive en el árbol git en absoluto — se publica como **asset adjunto a la Release** (`releases/download/<tag>/manifest.json`).

**Corrección:** `fetch_release_manifest()` usa la **Releases API** (`/releases/tags/<tag>` o `/releases/latest`), localiza el asset por nombre en `release["assets"]` y lo descarga vía la URL de la API del asset con `Accept: application/octet-stream` (la URL pública de descarga no funciona con un token Bearer contra un repo privado). Para `sync-rules.yml` se pide siempre el tag exacto del payload — nunca `latest` —, así la autenticidad del manifest sigue atada a la versión concreta que se sincroniza aunque el transporte ya no sea git.

### 5.2 Fine-grained PAT no soporta Git LFS

**Decisión inicial:** `RULES_REPO_TOKEN` como fine-grained PAT con permiso `Contents: Read-only`, mínimo privilegio.

**Fallo real:** `git clone`/`sparse-checkout`/`checkout` funcionaban bien (git "normal"), pero `git lfs pull` fallaba con `Resource not accessible by personal access token`. Es una limitación documentada de GitHub: los fine-grained PAT no dan acceso a la API de Git LFS, sea cual sea el permiso marcado.

**Corrección:** `RULES_REPO_TOKEN` pasó a ser un **classic PAT con scope `repo`**. Contrapartida asumida conscientemente: da acceso de lectura/escritura a *todos* los repos privados de la cuenta (no hay scope más estrecho en classic), pero el script nunca lo usa para escribir — todas las operaciones con este token son de solo lectura (`clone`, `checkout`, `lfs pull`, lecturas de la Releases API). El `git push` hacia `watch_gate` usa el `GITHUB_TOKEN` automático de Actions, un secret completamente distinto.

### 5.3 "Cone mode leak": `rules/semgrep/config.yaml` se colaba sin pedirlo

**Fallo real:** al pedir una subcarpeta como `rules/semgrep/custom/python` en sparse-checkout modo **cone**, Git incluye automáticamente los ficheros sueltos de cada carpeta **ancestra** (`rules/semgrep/`, `rules/`) — ahí vive `config.yaml` (config de LiteLLM, sin relación con las reglas, explícitamente excluido desde el diseño inicial). El checkout intentaba resolver su contenido LFS y fallaba (`Resource not accessible...`), abortando toda la sincronización aunque nunca se hubiera pedido ese fichero.

**Corrección:** el checkout se hace con `git lfs install --skip-smudge` (deja todo como punteros de texto, nunca falla por red/permisos de un fichero que ni se pidió) y el contenido real se resuelve después con `git lfs pull --include=<únicamente las carpetas pedidas>`. `config.yaml` se queda como puntero sin resolver, nunca se descarga ni se copia a `watch_gate` — verificado con un test de integración real (`test_cone_mode_leaks_ancestor_file_but_it_stays_unresolved`).

### 5.4 Verificación por clave, todo-o-nada

Decisión que se mantuvo sin cambios: el hash se compara **por clave** (idioma custom / vendor+carpeta third-party / categoría YARA), nunca de forma global. Si una sola clave falla, no se activa **ninguna** — ni siquiera las que sí verificaron — y se listan explícitamente las claves que fallaron. El estado activo (`rules/.rules-state.json`) es **acumulativo**: cada sincronización parcial actualiza solo las claves que trajo, conservando el hash verificado de ejecuciones anteriores para las demás.

## 6. Verificación real (no solo revisión de código)

- **Tests unitarios** (32 casos, `tests/unit/test_sync_rules.py`): resolución de scope, verificación por hash (éxito, manipulación detectada, fallos independientes por clave), aplicación del contenido, estado acumulativo, `cmd_check`, Releases API mockeada, `cmd_sync` de punta a punta con doble de prueba para el checkout — incluyendo el caso crítico de que una clave manipulada no activa nada.
- **Tests de integración con Git+LFS real** (5 casos, `tests/unit/test_sync_rules_git_lfs.py`): contra un repo git+LFS local real (remoto `file://`, sin red ni token), reproduciendo los dos bugs de §5.2/§5.3 y confirmando que quedan resueltos.
- **Ejecución real en producción**: `reconcile-rules.yml` lanzado manualmente contra los repos reales, iterando sobre los tres fallos de §5 hasta dejarlo en verde. Resultado confirmado: versión `v0.0.2` activa, 17 lenguajes custom + 4 vendors third-party (35 carpetas) + 2 categorías YARA, todos con hash verificado, comiteado automáticamente por el propio workflow (commit `4ed07e4`).

## 7. Conexión con la capa estática (cerrado)

`watchgate/core/layers/static_layer.py` inicialmente solo cargaba `rules/semgrep/custom/<lenguaje>` (por una coincidencia de convenciones con `_get_rules_dir`, no por diseño deliberado) y cubría un mapa de lenguajes incompleto. Se conectó explícitamente con lo que sincroniza este flujo:

- **`THIRD_PARTY_LANGUAGE_MAP`**: tabla explícita (a mano, nunca adivinada por coincidencia de nombre — respetando que `<carpeta>` de third-party es un namespace independiente, p. ej. `trailofbits/rs` son reglas de Rust) que conecta cada lenguaje con sus carpetas third-party relevantes. Excluye a propósito los paquetes no específicos de un lenguaje (`generic`, `noisy`, `problem-based-packs`), que no encajan en un análisis por-fichero.
- `_run_semgrep_on_file` ahora incluye siempre `custom/<lenguaje>` + `custom/regex` (patrones de secretos, independiente del lenguaje) + las carpetas third-party relevantes.
- `_detect_language` ampliado de 11 a 28 extensiones/patrones: cubre los 17 lenguajes de `custom/` y los que solo tienen reglas third-party (kotlin, scala, solidity, terraform); Dockerfile se detecta por nombre de fichero, no por extensión.
- El fallback sin verificación (paso 4 de `_get_rules_dir`) ahora deja constancia explícita con `logger.warning` si se alcanza — sigue existiendo (es necesario para un consumidor externo del paquete sin el checkout ya sincronizado), pero nunca en silencio.

## 8. Capa YARA (cerrado)

Per spec §4, YARA no es una capa nueva ni independiente: es la MISMA capa `static` que Semgrep, combinada con `max()` (nunca sumar), bajo el mismo peso `static: 0.25` de `.watchgate.yml` — confirmado por el propio comentario del fichero de ejemplo (`# Semgrep / YARA sobre el código modificado`). Se implementó así, no como un quinto `@register_layer` aparte:

- `_get_compiled_yara_rules`: compila **todas** las categorías publicadas en `rules/yara/<categoria>/`, siempre (nunca selección parcial), con caché de proceso (compilar ~700 reglas no es gratis; se compila una vez por ejecución de `watchgate`, no por fichero).
- `_run_yara_on_text`: ejecuta el catálogo compilado sobre el mismo contenido que ve Semgrep (el `diff_hunk`), pero **sin filtrar por lenguaje** — a diferencia de Semgrep, que necesita `_detect_language` para elegir configuración. Un webshell puede llevar cualquier extensión, o ninguna; filtrar YARA por lenguaje habría anulado buena parte de su propósito.
- El `risk_score` de cada hallazgo se lee de los metadatos que la propia regla ya trae (`meta.risk_score`, calculado en el repo de reglas como `0.45*severity + 0.30*confidence + 0.25*exploitability`) — no se reinventa una tabla de severidad aparte como la de Semgrep. `threat_nature` es siempre `MALICIOUS` (el catálogo YARA aquí es enteramente de detección de malware/webshells/anti-análisis).
- `analyze()` combina los hallazgos de Semgrep y YARA en la misma lista y aplica el `max()` ya existente sobre el conjunto — verificado explícitamente que Semgrep(30) + YARA(83) da 83, nunca 113.

Verificado con reglas reales del repo (compilación de las 9 reglas ya sincronizadas + match real contra un webshell ASP legítimo, extrayendo `risk_score=83` de sus propios metadatos) y con tests unitarios que fijan el caso clave: un fichero `.asp` (extensión que Semgrep no reconoce) sigue detectándose vía YARA.

## 9. Pendiente / gaps conocidos

- **`sync-rules.yml` (el disparo real por `repository_dispatch`) todavía no se ha probado de punta a punta** — sí se validó `reconcile-rules.yml`, que comparte toda la lógica de sincronización, pero el disparo por evento en sí queda por confirmar (simulando el evento o publicando una release real desde el repo de reglas).

Este es el único punto pendiente de una siguiente iteración; no es un bug de lo entregado aquí.
