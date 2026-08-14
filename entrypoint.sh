#!/usr/bin/env bash
# Entrypoint de la GitHub Action "WatchGate Risk Scoring" (action.yml,
# using: 'composite'). Cliente ligero: calcula el diff con git puro y
# delega TODO el análisis (estático + semántico) al Engine API centralizado
# (docker/engine-api.Dockerfile, POST /api/v1/analyze -- ver
# watchgate/api/routers/analyze.py).
#
# Por qué NO se usa el paquete Python "watchgate" directamente: se
# descartó a propósito -- watchgate/core/layers/__init__.py importa
# incondicionalmente la capa semántica (chromadb/sentence-transformers/
# torch) a nivel de módulo en cuanto se importa `watchgate.core.layers` (lo
# hacen tanto `cli.py` como `adapters/github_action/main.py`), así que
# cualquier imagen ligera para este runner reventaría en el import antes de
# ejecutar una sola línea. Esta Action ni siquiera instala el paquete: solo
# necesita git/curl/jq, que ya vienen en los runners ubuntu-latest.
#
# Por qué git merge-base en vez de leer base_sha/head_sha directamente del
# evento de GitHub ($GITHUB_EVENT_PATH): el payload del evento pull_request
# trae `pull_request.base.sha`, pero ese SHA es el HEAD de la rama base EN
# EL MOMENTO EN QUE SE ABRIÓ/ACTUALIZÓ EL PR, no el ancestro común real con
# el HEAD actual -- si la rama base avanzó después (nuevos merges a main)
# sin que el autor rebasara, ese SHA ya no es un ancestro de HEAD y diffear
# contra él mezcla cambios ajenos al PR dentro del diff analizado. git
# merge-base calcula el ancestro común real en el momento de la ejecución,
# igual que haría `git diff` localmente.
set -euo pipefail

die() {
    echo "::error::WatchGate: $*" >&2
    exit 1
}

need_bin() {
    command -v "$1" >/dev/null 2>&1 || die "falta el binario '$1' en el runner."
}
need_bin git
need_bin curl
need_bin jq

: "${INPUT_GITHUB_TOKEN:?INPUT_GITHUB_TOKEN no está definida}"
: "${INPUT_ENGINE_API_URL:?INPUT_ENGINE_API_URL no está definida}"
: "${INPUT_ENGINE_API_KEY:?INPUT_ENGINE_API_KEY no está definida}"
: "${INPUT_BASE_REF:=main}"
: "${INPUT_RISK_THRESHOLD:=70}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY no está definida -- ¿se ejecuta fuera de GitHub Actions?}"
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT no está definida -- ¿se ejecuta fuera de GitHub Actions?}"

engine_api_url="${INPUT_ENGINE_API_URL%/}" # sin barra final, evita "//api/v1/..."
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

# ---------------------------------------------------------------------------
# 1. Resolver base_sha / head_sha solo con git (sin API de GitHub)
# ---------------------------------------------------------------------------
if [ "$(git rev-parse --is-shallow-repository 2>/dev/null || echo false)" = "true" ]; then
    # actions/checkout@v4 sin fetch-depth: 0 deja un clon superficial --
    # merge-base necesita el histórico real para encontrar el ancestro
    # común, no solo el último commit.
    git fetch --unshallow --quiet
fi
git fetch origin "$INPUT_BASE_REF" --quiet

head_sha="$(git rev-parse HEAD)"
base_sha="$(git merge-base "origin/$INPUT_BASE_REF" HEAD)" \
    || die "no se pudo calcular 'git merge-base origin/$INPUT_BASE_REF HEAD' -- ¿existe esa rama en origin?"

[ -n "$head_sha" ] || die "head_sha vacío tras 'git rev-parse HEAD'."
[ -n "$base_sha" ] || die "base_sha vacío tras 'git merge-base'."

# ---------------------------------------------------------------------------
# 2. Generar el diff
# ---------------------------------------------------------------------------
changed_files_file="$workdir/changed_files.txt"
diff_file="$workdir/diff.patch"
git diff --name-only "$base_sha" "$head_sha" > "$changed_files_file"
git diff -U3 "$base_sha" "$head_sha" > "$diff_file"

if [ ! -s "$diff_file" ]; then
    # Sin cambios reales entre base y head (ej. merge commit vacío, PR de
    # solo metadatos) -- no tiene sentido gastar presupuesto de tokens del
    # Engine API en un diff vacío. score=0 y result mínimo, para que un
    # paso posterior del workflow que siempre lea ambos outputs no falle
    # por output ausente.
    {
        echo "score=0"
        echo "result={\"score\":0,\"skipped\":true,\"reason\":\"sin cambios entre $base_sha y $head_sha\"}"
    } >> "$GITHUB_OUTPUT"
    echo "WatchGate: sin cambios en el diff, análisis omitido."
    exit 0
fi

# ---------------------------------------------------------------------------
# 3. Construir el payload (esquema real de AnalyzeRequest, ver PARTE 0:
#    NO existe "changed_files" ni "repo"/"pr_number" a nivel raíz -- "repo"
#    y "pr_id" van dentro de "metadata", como hace cli.py/main.py).
# ---------------------------------------------------------------------------
pr_number=""
author_login=""
if [ -n "${GITHUB_EVENT_PATH:-}" ] && [ -f "${GITHUB_EVENT_PATH:-}" ]; then
    pr_number="$(jq -r '.pull_request.number // empty' "$GITHUB_EVENT_PATH")"
    author_login="$(jq -r '.pull_request.user.login // empty' "$GITHUB_EVENT_PATH")"
fi
if [ -z "$author_login" ]; then
    author_login="${GITHUB_ACTOR:-}"
fi

payload_file="$workdir/payload.json"
jq -n \
    --rawfile diff_text "$diff_file" \
    --arg base_sha "$base_sha" \
    --arg head_sha "$head_sha" \
    --arg repo_path "$GITHUB_REPOSITORY" \
    --arg repo "$GITHUB_REPOSITORY" \
    --arg pr_id "$pr_number" \
    --arg author_login "$author_login" \
    '{
        diff_text: $diff_text,
        base_sha: $base_sha,
        head_sha: $head_sha,
        repo_path: $repo_path,
        metadata: { repo: $repo, pr_id: $pr_id, author_login: $author_login }
    }' > "$payload_file"

# ---------------------------------------------------------------------------
# 4. Llamar al Engine API
# ---------------------------------------------------------------------------
response_file="$workdir/response.json"
http_code="$(curl -sS -o "$response_file" -w '%{http_code}' \
    --max-time 120 \
    -X POST "$engine_api_url/api/v1/analyze" \
    -H "Authorization: Bearer $INPUT_ENGINE_API_KEY" \
    -H "Content-Type: application/json" \
    --data @"$payload_file")" \
    || die "fallo de red llamando al Engine API en '$engine_api_url/api/v1/analyze'."

if [ "$http_code" -lt 200 ] || [ "$http_code" -ge 300 ]; then
    die "Engine API devolvió HTTP $http_code. Respuesta: $(cat "$response_file")"
fi

# ---------------------------------------------------------------------------
# 5. Validar que la respuesta trae un score válido (0-100)
# ---------------------------------------------------------------------------
score="$(jq -r '.score // empty' "$response_file")"
if [ -z "$score" ] || ! [[ "$score" =~ ^[0-9]+$ ]] || [ "$score" -gt 100 ]; then
    die "respuesta del Engine API sin 'score' numérico válido (0-100). Respuesta completa: $(cat "$response_file")"
fi

# ---------------------------------------------------------------------------
# 6. Escribir outputs (score + result completo)
# ---------------------------------------------------------------------------
result_json="$(cat "$response_file")"
# Delimitador aleatorio para el bloque multilínea de $GITHUB_OUTPUT -- un
# delimitador fijo tipo "EOF" es inseguro aquí: `justification` la escribe
# el LLM de la capa semántica y podría contener esa cadena literal.
delimiter="WATCHGATE_RESULT_${RANDOM}_$$"
{
    echo "score=$score"
    echo "result<<$delimiter"
    echo "$result_json"
    echo "$delimiter"
} >> "$GITHUB_OUTPUT"

# ---------------------------------------------------------------------------
# 7. Publicar el Check Run
# ---------------------------------------------------------------------------
conclusion="success"
if [ "$score" -ge "$INPUT_RISK_THRESHOLD" ]; then
    conclusion="failure"
fi

summary="$(jq -r --arg score "$score" --arg semaforo "$(jq -r '.semaforo // "?"' "$response_file")" '
    "**Score final:** \($score)/100  ·  **Semáforo:** \($semaforo)\n\n" +
    "| Capa | Risk score | Estado | Justificación |\n" +
    "|---|---|---|---|\n" +
    ((.layer_results // {}) | to_entries | map(
        "| " + .key
        + " | " + ((.value.risk_score // 0) | tostring)
        + " | " + (if .value.skipped then "omitida" else "ejecutada" end)
        + " | " + ((.value.justification // "-") | gsub("\n"; " ") | gsub("\\|"; "\\|") | .[0:200])
        + " |"
    ) | join("\n"))
' "$response_file")"

check_payload_file="$workdir/check_payload.json"
jq -n \
    --arg name "WatchGate Risk Scoring" \
    --arg head_sha "$head_sha" \
    --arg conclusion "$conclusion" \
    --arg title "WatchGate: $score/100 ($conclusion)" \
    --arg summary "$summary" \
    '{
        name: $name,
        head_sha: $head_sha,
        status: "completed",
        conclusion: $conclusion,
        output: { title: $title, summary: $summary }
    }' > "$check_payload_file"

check_response_file="$workdir/check_response.json"
check_http_code="$(curl -sS -o "$check_response_file" -w '%{http_code}' \
    --max-time 30 \
    -X POST "https://api.github.com/repos/$GITHUB_REPOSITORY/check-runs" \
    -H "Authorization: Bearer $INPUT_GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    --data @"$check_payload_file")" \
    || die "fallo de red publicando el Check Run en la API de GitHub."

if [ "$check_http_code" -lt 200 ] || [ "$check_http_code" -ge 300 ]; then
    die "no se pudo publicar el Check Run (HTTP $check_http_code). Respuesta: $(cat "$check_response_file")"
fi

echo "WatchGate: score=$score/100, conclusion=$conclusion (umbral=$INPUT_RISK_THRESHOLD)"

# ---------------------------------------------------------------------------
# 8. Propagar el fallo al job del workflow consumidor
# ---------------------------------------------------------------------------
if [ "$conclusion" = "failure" ]; then
    die "score $score >= risk-threshold $INPUT_RISK_THRESHOLD."
fi

exit 0
