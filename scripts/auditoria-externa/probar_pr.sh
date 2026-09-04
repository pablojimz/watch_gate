#!/usr/bin/env bash
# probar_pr.sh -- analiza UNA sola PR concreta con la CLI de watchgate,
# fuera de la auditoría masiva. Útil para reproducir/depurar un caso
# puntual (ver conversación: PR de openclaw/openclaw con diff sospechoso).
#
# USO:
#   ./probar_pr.sh <owner>/<repo> <pr_number> [author_login]
#
# Ejemplo:
#   ./probar_pr.sh openclaw/openclaw 137641 ly85206559

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FORMATTER="$SCRIPT_DIR/format_result.py"

if [[ $# -lt 2 ]]; then
    echo "Uso: $0 <owner>/<repo> <pr_number> [author_login]" >&2
    exit 2
fi

repo_full="$1"
pr_number="$2"
pr_author="${3:-desconocido}"
owner="${repo_full%%/*}"
repo="${repo_full#*/}"
pr_url="https://github.com/$owner/$repo/pull/$pr_number"

command -v watchgate >/dev/null 2>&1 || { echo "ERROR: 'watchgate' no está en PATH." >&2; exit 1; }
command -v gh >/dev/null 2>&1 || { echo "ERROR: 'gh' no está instalado." >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "ERROR: 'gh' no está autenticado -- ejecuta: gh auth login" >&2; exit 1; }

GH_TOKEN_VALUE="$(gh auth token 2>/dev/null || true)"
if [[ -n "$GH_TOKEN_VALUE" ]]; then
    export GITHUB_TOKEN="$GH_TOKEN_VALUE"
    export WATCHGATE_GITHUB_TOKEN="$GH_TOKEN_VALUE"
fi

# Cargar WATCHGATE_LLM_* del .env del proyecto (igual que auditar_prs.sh)
# para que la capa semántica funcione.
ENV_FILE="$REPO_ROOT/.env"
if [[ -f "$ENV_FILE" ]]; then
    while IFS='=' read -r key value; do
        [[ -n "$value" ]] || continue
        [[ -n "${!key:-}" ]] && continue
        export "$key=$value"
    done < <(grep -E '^WATCHGATE_LLM_[A-Z_]+=' "$ENV_FILE")
fi

echo "[probar_pr] Descargando diff de $owner/$repo#$pr_number..." >&2
diff_text="$(gh api "repos/$owner/$repo/pulls/$pr_number" -H "Accept: application/vnd.github.v3.diff")" \
    || { echo "ERROR: no se pudo descargar el diff (¿PR existe? ¿repo privado?)." >&2; exit 1; }

expected_files="$(gh api "repos/$owner/$repo/pulls/$pr_number" --jq '.changed_files' 2>/dev/null || echo '?')"
actual_files="$(grep -c '^diff --git ' <<< "$diff_text")"
echo "[probar_pr] Ficheros: GitHub dice $expected_files, el diff descargado trae $actual_files." >&2
if [[ "$expected_files" =~ ^[0-9]+$ && "$actual_files" != "$expected_files" ]]; then
    echo "[probar_pr] AVISO: no coinciden -- este diff podría no ser el real de esta PR." >&2
fi

echo "[probar_pr] Analizando..." >&2
printf '%s\n' "$diff_text" | watchgate analyze \
    --diff-stdin \
    --repo "$owner/$repo" \
    --pr-id "$pr_number" \
    --author-login "$pr_author" \
    --format json \
    --quiet \
    | python3 "$FORMATTER" "$pr_number" "$pr_author" "$pr_url"
