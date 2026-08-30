#!/usr/bin/env bash
# Instala el hook pre-receive de WatchGate (./pre-receive, en este mismo
# directorio) en un repo concreto del contenedor Forgejo, y le fija su
# propia API key (una por repo -- ver la puerta clave<->repo de
# watchgate/api/routers/analyze.py::ensure_api_key_repo_binding, que exige
# que la key esté atada al MonitoredRepo exacto que se está analizando).
#
# Uso (desde la raíz del repo watch_gate, con `docker compose -f
# docker-compose.yml -f docker-compose.gitserver.yml up -d forgejo` ya
# levantado):
#   ./docker/git-server-hooks/install.sh <owner>/<repo> <api_key>
#
# La API key se obtiene con provision_repo.sh (mismo directorio), que crea
# el MonitoredRepo + la key atada a él.
set -euo pipefail

if [ $# -ne 2 ]; then
    echo "Uso: $0 <owner>/<repo> <api_key>" >&2
    exit 1
fi

full_name="$1"
api_key="$2"
# Fichero fuente único, empaquetado dentro de `watchgate` para poder
# servirlo también por HTTP (GET /api/v1/hooks/pre-receive) a servidores
# Git reales que no tienen este repo clonado -- ver la cabecera del propio
# script y docs/manual_git_hooks.md §6.3.
hook_src="$(dirname "$0")/../../watchgate/adapters/git_hook/pre_receive_hook.sh"
repo_git_dir="/data/git/repositories/${full_name}.git"

compose=(docker compose -f docker-compose.yml -f docker-compose.gitserver.yml)

"${compose[@]}" cp "$hook_src" "forgejo:${repo_git_dir}/hooks/pre-receive.d/watchgate"

# `docker compose cp` copia como root; el hook lo ejecuta git diff-tree
# como usuario `git`, así que hace falta devolverle la propiedad -- `chmod`
# como `git` sobre un fichero que ahora es de `root` falla con "Operation
# not permitted" (verificado en vivo), de ahí que este bloque corra como
# root (sin `-u git`) y sea el que hace el `chown` explícito.
#
# Auditoría: antes `repo_git_dir`/`api_key` se interpolaban directamente
# dentro de la cadena de `sh -c "..."` -- un `full_name` con una comilla
# simple (p. ej. si Forgejo permitiera nombres de repo autoservicio con
# caracteres arbitrarios) rompía el quoting e inyectaba shell arbitrario,
# ejecutado como root dentro del contenedor de Forgejo. El script en sí
# va entre comillas SIMPLES (sin expansión de bash), y los valores viajan
# como argumentos posicionales reales ($1/$2) en vez de texto interpolado
# -- ningún carácter de `full_name`/`api_key` se interpreta como sintaxis
# de shell, se pase lo que se pase.
"${compose[@]}" exec -T forgejo sh -c '
    chown git:git "$1/hooks/pre-receive.d/watchgate" &&
    chmod +x "$1/hooks/pre-receive.d/watchgate" &&
    printf "WATCHGATE_ENGINE_API_KEY=%s\n" "$2" > "$1/hooks/watchgate.env" &&
    chown git:git "$1/hooks/watchgate.env"
' _ "$repo_git_dir" "$api_key"

echo "Hook instalado en ${repo_git_dir}/hooks/pre-receive.d/watchgate"
