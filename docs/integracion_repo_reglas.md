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

## 7. Pendiente / gaps conocidos

- **`sync-rules.yml` (el disparo real por `repository_dispatch`) todavía no se ha probado de punta a punta** — sí se validó `reconcile-rules.yml`, que comparte toda la lógica de sincronización, pero el disparo por evento en sí queda por confirmar (simulando el evento o publicando una release real desde el repo de reglas).
- **La capa estática (`watchgate/core/layers/static_layer.py`) no usa todavía las reglas third-party ni YARA.** Su resolución de directorio (`_get_rules_dir`) prioriza `rules/semgrep/` local, así que en la práctica ya usa las reglas `custom/<lenguaje>` verificadas y activadas por este flujo -- pero:
  - Solo carga `rules/semgrep/custom/<lenguaje>`; nunca toca `rules/semgrep/third-party/<vendor>/<carpeta>`, aunque este flujo ya sincroniza y verifica 4 vendors / 35 carpetas.
  - Su mapa de detección de lenguaje (`_detect_language`) no cubre los 17 lenguajes disponibles en `custom/` (faltan, entre otros, dockerfile, csharp, rust, swift, php, powershell).
  - Su ruta de fallback (paso 4 de `_get_rules_dir`) sigue haciendo su propio `git clone` del repo de reglas si `rules/semgrep/` no existiera localmente -- sin pasar por ninguna verificación de hash, lo cual contradice el requisito de que el análisis de PRs use siempre la versión activa *verificada*. En la práctica no se activa (el paso 3 siempre encuentra contenido, ya poblado por este flujo), pero sigue siendo una ruta de código sin blindar.
  - **No existe ninguna capa YARA** en el código Python de `watchgate` todavía. `rules/yara/<categoria>/` queda poblado y verificado por este flujo, listo para cuando se implemente esa capa, pero hoy no lo usa nadie.

Estos cuatro puntos son candidatos naturales para una siguiente iteración, no bugs de lo entregado aquí.
