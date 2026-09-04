#!/usr/bin/env bash
# auditar_prs.sh
#
# Auditoría externa con la CLI de WatchGate (`watchgate analyze`), sobre PRs
# REALES de cada repo (no el repo entero como diff gigante -- eso es lo que
# hacía auditar_repos.sh, y rompía los supuestos del pipeline).
#
# Dos fases, cada una paralelizada por separado:
#   FASE 1 (listado): por cada repo, lista sus N PRs abiertas más
#     recientemente actualizadas (gh api .../pulls?state=open&sort=updated).
#     Rápido -- una llamada API por repo.
#   FASE 2 (análisis): TODAS las PRs de TODOS los repos se aplanan en una
#     única cola y se analizan en paralelo con `xargs -P`, no repo por repo.
#     Esto importa porque cada `watchgate analyze` es un proceso nuevo que
#     recompila el catálogo de Semgrep desde cero (~20-60s fijos, medido en
#     vivo, ver rules/semgrep y el comentario en
#     watchgate/core/layers/static_layer.py:123-135) -- CASI INDEPENDIENTE
#     del tamaño del diff. Si se paralelizara solo por repo, un repo con 5
#     PRs bloquea su hueco ~5x ese coste fijo aunque haya cores libres; al
#     aplanar por PR, todas avanzan a la vez.
#
# El diff de cada PR se pide directamente a la API de GitHub (Accept:
# application/vnd.github.v3.diff) -- sin clonar el repo.
#
# Requiere `gh` autenticado (`gh auth status`) y `jq`. El token de `gh` se
# reexporta como GITHUB_TOKEN/WATCHGATE_GITHUB_TOKEN para que la propia CLI
# de WatchGate lo use en sus llamadas a la API de GitHub (reputación).
#
# `resultados.txt` SOLO contiene análisis con veredicto real (exit 0 ó 1).
# El stderr de cada proceso (barras de progreso, warnings de logging -- la
# causa de los caracteres raros de antes) nunca se mezcla con el resultado.
# Cualquier fallo (listar PRs, obtener diff, timeout, exit code de error)
# se registra en errores.txt y queda fuera de resultados.txt.
#
# USO:
#   ./auditar_prs.sh
#
# VARIABLES DE ENTORNO (todas opcionales):
#   LINKS_FILE        Listado de repos (default: top-100-github-links.txt)
#   PARALLEL_JOBS      Nº de análisis EN PARALELO -- ahora por PR, no por
#                      repo (default: nproc). El cuello de botella real
#                      (Semgrep) espera más en E/S y subproceso que en CPU
#                      pura, así que subir esto por encima de nproc suele
#                      seguir dando ganancia real; prueba 8-12 en una
#                      máquina de 4 cores antes de asumir que no ayuda.
#   LIMIT               Analiza solo los N primeros repos del listado (default: 0 = todos)
#   PRS_PER_REPO       Nº máx. de PRs abiertas a auditar por repo (default: 5)
#   API_TIMEOUT         Timeout en segundos por llamada a la API de GitHub (default: 30)
#   ANALYZE_TIMEOUT    Timeout en segundos por análisis de una PR (default: 300)
#   DISABLE_SEMANTIC   1 para desactivar la capa semántica/LLM (--weight semantic=0),
#                      0 para dejarla activa (default: 0 -- activa)
#   DISABLE_STATIC     1 para desactivar la capa estática/Semgrep (--weight static=0)
#                      -- es la responsable del coste fijo de ~20-60s por PR;
#                      desactivarla es la forma más directa de ir rápido a
#                      costa de perder esa capa (default: 0 -- activa)
#
# Ejemplos:
#   LIMIT=10 PRS_PER_REPO=3 ./auditar_prs.sh
#   PARALLEL_JOBS=10 ./auditar_prs.sh
#   DISABLE_STATIC=1 PARALLEL_JOBS=10 ./auditar_prs.sh   # pasada rápida
#
# SALIDA:
#   resultados.txt  -- un bloque por repo con sus PRs auditadas CON ÉXITO,
#                       en el orden del ranking original y con las PRs de
#                       cada repo en el mismo orden en que se listaron.
#   errores.txt      -- una línea por cada fallo (repo o PR concreta).
# Progreso en stderr mientras corre.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LINKS_FILE="${LINKS_FILE:-$SCRIPT_DIR/top-100-github-links.txt}"
RESULTS_FILE="$SCRIPT_DIR/resultados.txt"
ERRORS_FILE="$SCRIPT_DIR/errores.txt"

PARALLEL_JOBS="${PARALLEL_JOBS:-$(nproc 2>/dev/null || echo 4)}"
LIMIT="${LIMIT:-0}"
PRS_PER_REPO="${PRS_PER_REPO:-5}"
API_TIMEOUT="${API_TIMEOUT:-30}"
ANALYZE_TIMEOUT="${ANALYZE_TIMEOUT:-300}"
DISABLE_SEMANTIC="${DISABLE_SEMANTIC:-0}"
DISABLE_STATIC="${DISABLE_STATIC:-0}"
# .env del proyecto watch_gate: trae WATCHGATE_LLM_PROVIDER/API_KEY/etc. La
# CLI (`watchgate/cli.py`) NO carga .env sola (no hay python-dotenv/
# pydantic-settings env_file) -- sin esto, la capa semántica siempre se
# marca "omitida: Could not resolve authentication method", venga o no
# venga configurada realmente. Solo se cargan las claves WATCHGATE_LLM_*
# (no el resto del .env: DB, OAuth, webhooks... no hacen falta para
# `watchgate analyze` y no tiene sentido exponerlas a este proceso).
WATCHGATE_ENV_FILE="${WATCHGATE_ENV_FILE:-$(cd "$SCRIPT_DIR/../.." && pwd)/.env}"

FORMATTER="$SCRIPT_DIR/format_result.py"

command -v watchgate >/dev/null 2>&1 || { echo "ERROR: 'watchgate' no está en PATH." >&2; exit 1; }
command -v gh >/dev/null 2>&1 || { echo "ERROR: 'gh' (GitHub CLI) no está instalado." >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "ERROR: 'jq' no está instalado." >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: 'python3' no está instalado." >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "ERROR: 'gh' no está autenticado (gh auth login)." >&2; exit 1; }
[[ -f "$LINKS_FILE" ]] || { echo "ERROR: no se encuentra el listado de repos en $LINKS_FILE" >&2; exit 1; }
[[ -f "$FORMATTER" ]] || { echo "ERROR: no se encuentra $FORMATTER" >&2; exit 1; }

# Reexportar el token de gh para que la propia CLI de watchgate lo use
# (cascada de credenciales, ver watchgate/dashboard/backend/db.py) al pedir
# metadata de reputación del autor de cada PR.
GH_TOKEN_VALUE="$(gh auth token 2>/dev/null || true)"
if [[ -n "$GH_TOKEN_VALUE" ]]; then
    export GITHUB_TOKEN="$GH_TOKEN_VALUE"
    export WATCHGATE_GITHUB_TOKEN="$GH_TOKEN_VALUE"
fi

# Cargar WATCHGATE_LLM_* desde el .env del proyecto (ver comentario junto a
# WATCHGATE_ENV_FILE más arriba). No pisa una variable que ya venga puesta
# en el entorno de quien lanza el script (para poder seguir sobreescribiendo
# el proveedor/clave a mano sin tocar este fichero).
llm_vars_loaded=0
if [[ -f "$WATCHGATE_ENV_FILE" ]]; then
    while IFS='=' read -r key value; do
        [[ -n "$value" ]] || continue
        [[ -n "${!key:-}" ]] && continue
        export "$key=$value"
        llm_vars_loaded=$((llm_vars_loaded + 1))
    done < <(grep -E '^WATCHGATE_LLM_[A-Z_]+=' "$WATCHGATE_ENV_FILE")
fi
if [[ $llm_vars_loaded -gt 0 ]]; then
    echo "[WatchGate] Capa semántica: $llm_vars_loaded variable(s) WATCHGATE_LLM_* cargadas desde $WATCHGATE_ENV_FILE (proveedor: ${WATCHGATE_LLM_PROVIDER:-anthropic})." >&2
elif [[ "$DISABLE_SEMANTIC" != "1" ]]; then
    echo "[WatchGate] AVISO: no se encontraron variables WATCHGATE_LLM_* en $WATCHGATE_ENV_FILE (ni ya puestas en el entorno) -- la capa semántica se marcará 'omitida' en todos los análisis." >&2
fi

: > "$ERRORS_FILE"

WORK_DIR="$(mktemp -d)"
META_DIR="$WORK_DIR/meta"       # 1 fichero por repo: n|owner|repo|url|pr_count
QUEUE_DIR="$WORK_DIR/queue"     # 1 fichero por repo: líneas TSV de sus PRs (orden de listado)
OUT_DIR="$WORK_DIR/salidas"     # 1 fichero por PR analizada con éxito
mkdir -p "$META_DIR" "$QUEUE_DIR" "$OUT_DIR"

# --- FASE 1: listar las PRs abiertas de un repo (rápido, una llamada API) ---
list_repo_prs() {
    local line="$1"
    local n url owner repo prs_json pr_count
    n="${line%%.*}"
    url="${line#*. }"
    url="${url%/}"
    owner="$(basename "$(dirname "$url")")"
    repo="$(basename "$url")"

    prs_json="$(timeout "$API_TIMEOUT" gh api \
        "repos/$owner/$repo/pulls" \
        -X GET -f state=open -f sort=updated -f direction=desc -f per_page="$PRS_PER_REPO" \
        2>/dev/null)"
    if [[ $? -ne 0 ]]; then
        echo "$n|$owner|$repo|$url|ERROR" > "$META_DIR/$(printf '%03d' "$n").meta"
        echo "[$n/100] $owner/$repo -- no se pudo listar PRs abiertas" >> "$ERRORS_FILE"
        return
    fi

    pr_count="$(echo "$prs_json" | jq 'length' 2>/dev/null || echo 0)"
    echo "$n|$owner|$repo|$url|$pr_count" > "$META_DIR/$(printf '%03d' "$n").meta"

    if [[ "$pr_count" -gt 0 ]]; then
        echo "$prs_json" | jq -r --arg n "$n" --arg owner "$owner" --arg repo "$repo" \
            '.[] | [$n, $owner, $repo, .number, .user.login, .html_url] | @tsv' \
            > "$QUEUE_DIR/$(printf '%03d' "$n").queue"
    fi
}
export -f list_repo_prs
export META_DIR QUEUE_DIR API_TIMEOUT PRS_PER_REPO ERRORS_FILE

# --- FASE 2: analizar UNA PR (una línea TSV: n, owner, repo, pr_number, pr_author, pr_url) ---
# Usa --format json (nunca se redacta, a diferencia de --format comment) y
# formatea el resultado con format_result.py -- así se ve el desglose
# completo (capas + justificación + findings) también en los casos que
# `render_comment` colapsaría a un mensaje genérico por threat_summary.
# malicioso > 0. Esa redacción tiene sentido de cara a un comentario PÚBLICO
# en GitHub (no darle pistas a un atacante); aquí es un informe de auditoría
# interno, así que no aplica.
analyze_one_pr() {
    local n owner repo pr_number pr_author pr_url diff_text json_output rc reason
    local -a weight_args
    IFS=$'\t' read -r n owner repo pr_number pr_author pr_url <<< "$1"

    diff_text="$(timeout "$API_TIMEOUT" gh api \
        "repos/$owner/$repo/pulls/$pr_number" \
        -H "Accept: application/vnd.github.v3.diff" 2>/dev/null)"
    if [[ $? -ne 0 || -z "$diff_text" ]]; then
        echo "[$n/100] $owner/$repo PR #$pr_number -- no se pudo obtener el diff" >> "$ERRORS_FILE"
        return
    fi

    weight_args=()
    [[ "$DISABLE_SEMANTIC" == "1" ]] && weight_args+=(--weight "semantic=0")
    [[ "$DISABLE_STATIC" == "1" ]] && weight_args+=(--weight "static=0")

    json_output="$(printf '%s\n' "$diff_text" | timeout "$ANALYZE_TIMEOUT" watchgate analyze \
        --diff-stdin \
        --repo "$owner/$repo" \
        --pr-id "$pr_number" \
        --author-login "$pr_author" \
        --format json \
        --quiet \
        "${weight_args[@]}" 2>/dev/null)"
    rc=$?

    if [[ $rc -eq 0 || $rc -eq 1 ]]; then
        printf '%s' "$json_output" | python3 "$FORMATTER" "$pr_number" "$pr_author" "$pr_url" \
            > "$OUT_DIR/$(printf '%03d' "$n")-${pr_number}.txt"
        echo "" >> "$OUT_DIR/$(printf '%03d' "$n")-${pr_number}.txt"
        echo "[$n/100] $owner/$repo PR #$pr_number -> veredicto OK" >&2
    else
        reason="exit code $rc"
        [[ $rc -eq 124 ]] && reason="timeout (${ANALYZE_TIMEOUT}s)"
        echo "[$n/100] $owner/$repo PR #$pr_number -- fallo en el análisis ($reason)" >> "$ERRORS_FILE"
        echo "[$n/100] $owner/$repo PR #$pr_number -> fallo ($reason)" >&2
    fi
}
export -f analyze_one_pr
export OUT_DIR API_TIMEOUT ANALYZE_TIMEOUT DISABLE_SEMANTIC DISABLE_STATIC ERRORS_FILE FORMATTER

# --- Cargar listado de repos y aplicar LIMIT si procede ---
mapfile -t LINES < "$LINKS_FILE"
if [[ "$LIMIT" -gt 0 && "$LIMIT" -lt "${#LINES[@]}" ]]; then
    LINES=("${LINES[@]:0:$LIMIT}")
fi

echo "[WatchGate] Fase 1/2: listando PRs abiertas de ${#LINES[@]} repos..." >&2
printf '%s\n' "${LINES[@]}" | xargs -d '\n' -I{} -P "$PARALLEL_JOBS" bash -c 'list_repo_prs "$@"' _ {}

# --- Aplanar todas las PRs de todos los repos en una única cola ---
QUEUE_FILE="$WORK_DIR/queue.tsv"
: > "$QUEUE_FILE"
shopt -s nullglob
for f in "$QUEUE_DIR"/*.queue; do
    cat "$f" >> "$QUEUE_FILE"
done
shopt -u nullglob

n_prs="$(wc -l < "$QUEUE_FILE" | tr -d ' ')"
echo "[WatchGate] Fase 2/2: analizando $n_prs PR(s) en paralelo ($PARALLEL_JOBS a la vez; semántica: $([[ "$DISABLE_SEMANTIC" == "1" ]] && echo desactivada || echo activa); estática: $([[ "$DISABLE_STATIC" == "1" ]] && echo desactivada || echo activa))..." >&2

if [[ "$n_prs" -gt 0 ]]; then
    xargs -d '\n' -I{} -P "$PARALLEL_JOBS" bash -c 'analyze_one_pr "$@"' _ {} < "$QUEUE_FILE"
fi

# --- Consolidar resultados.txt en el orden original del ranking, y dentro
#     de cada repo en el mismo orden en que se listaron sus PRs ---
{
    echo "Auditoría externa WatchGate -- PRs abiertas de ${#LINES[@]} repos de GitHub (por estrellas)"
    echo "Generado: $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    echo "Máx. PRs por repo: $PRS_PER_REPO | Semántica: $([[ "$DISABLE_SEMANTIC" == "1" ]] && echo desactivada || echo activa) | Estática: $([[ "$DISABLE_STATIC" == "1" ]] && echo desactivada || echo activa)"
    echo "========================================================================"
    echo ""
} > "$RESULTS_FILE"

for line in "${LINES[@]}"; do
    n="${line%%.*}"
    padded="$(printf '%03d' "$n")"
    meta_file="$META_DIR/${padded}.meta"
    [[ -f "$meta_file" ]] || continue  # el repo ni siquiera llegó a listarse (no debería pasar)
    IFS='|' read -r _ owner repo url pr_count < "$meta_file"

    if [[ "$pr_count" == "ERROR" ]]; then
        continue  # fallo de listado -> solo en errores.txt, ver introducción del fichero
    fi

    header="== [$n/100] $owner/$repo ==
URL: $url
"
    if [[ "$pr_count" -eq 0 ]]; then
        {
            echo "$header"
            echo "[INFO] $owner/$repo no tiene PRs abiertas -- nada que auditar."
            echo ""
        } >> "$RESULTS_FILE"
        continue
    fi

    queue_file="$QUEUE_DIR/${padded}.queue"
    ok_count=0
    block=""
    while IFS=$'\t' read -r _ _ _ pr_number _ _; do
        pr_out="$OUT_DIR/${padded}-${pr_number}.txt"
        if [[ -f "$pr_out" ]]; then
            block+="$(cat "$pr_out")
"
            ok_count=$((ok_count + 1))
        fi
    done < "$queue_file"

    if [[ $ok_count -gt 0 ]]; then
        {
            echo "$header"
            echo "[INFO] $ok_count/$pr_count PR(s) auditadas con éxito (de un máx. de $PRS_PER_REPO)."
            echo ""
            printf '%s\n' "$block"
        } >> "$RESULTS_FILE"
    fi
done

rm -rf "$WORK_DIR"
n_errores="$(wc -l < "$ERRORS_FILE" | tr -d ' ')"
echo "[WatchGate] Hecho. Resultados en: $RESULTS_FILE ($n_errores fallo(s) registrados en $ERRORS_FILE)" >&2
