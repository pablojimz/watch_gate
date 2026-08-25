# Imagen de Forgejo (servidor Git propio, tipo GitLab/Gitea) para probar en
# local el flujo de hook `pre-receive` contra un servidor Git real -- ver
# docs/manual_git_hooks.md §6. La imagen oficial trae `curl` pero no `jq`,
# que el hook de docker/git-server-hooks/pre-receive necesita para parsear
# la respuesta JSON del Engine API.
FROM codeberg.org/forgejo/forgejo:10

RUN apk add --no-cache jq
