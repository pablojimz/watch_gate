Haz una auditoría de estado del flujo de "escaneo de PRs disparado desde el
propio dashboard" (repos conectados manualmente + botón de escaneo) -- NO
hagas cambios de código, esto es solo un diagnóstico. Al final quiero un
informe escrito, no un PR.

Los ficheros que componen este flujo, revísalos todos:
- watchgate/dashboard/backend/routers/repos.py (endpoints
  POST/GET /api/repos/external, POST /api/repos/external/{id}/scan)
- watchgate/dashboard/backend/routers/webhooks.py (webhook de GitHub que
  también dispara este mismo flujo para repos "managed")
- watchgate/dashboard/backend/tasks.py (run_managed_scan, run_audit_scan --
  las funciones que de verdad ejecutan el análisis en el worker)
- watchgate/db/models.py (MonitoredRepo -- el modelo que representa un
  "repo conectado")
- watchgate/dashboard/frontend/src/pages/ExternalReposPage.tsx (la pantalla
  donde el usuario conecta repos y lanza escaneos)
- watchgate/dashboard/frontend/src/api/client.ts (funciones
  listExternalRepos / addExternalRepo / scanExternalRepo)

Cosas concretas que quiero que compruebes y me confirmes con evidencia
(cita el fichero y la línea, no solo "parece que funciona"):

1. Cableado end-to-end: cuando el usuario pulsa "Scan" en el frontend,
   sigue el camino completo hasta que el resultado queda guardado en
   pr_scores -- confirma que cada paso realmente llama al siguiente (no
   asumas, sigue el código de verdad).

2. Manejo de errores: si run_audit_scan/run_managed_scan lanza una
   excepción (token inválido, PR inexistente, fallo de red al llamar a la
   API de GitHub...), ¿qué pasa exactamente? ¿Se captura en algún sitio?
   ¿Queda registrada en algún log? ¿Se refleja de alguna forma visible para
   el usuario, o desaparece en silencio?

3. Campo MonitoredRepo.status: comprueba si algún código en todo el repo
   escribe alguna vez un valor distinto de "active" en este campo (busca
   con grep todas las asignaciones a `.status` sobre un MonitoredRepo). Dime
   si es un campo que se actualiza de verdad o si está muerto.

4. Feedback al usuario tras encolar un scan: en ExternalReposPage.tsx,
   confirma si hay algún polling, refresco automático o websocket que
   avise cuando el job terminó (éxito o error), o si el usuario se queda
   sin ninguna señal después del toast inicial de "encolado".

5. Estado real de la infraestructura, si tienes forma de comprobarlo (por
   ejemplo si hay un `docker compose ps` accesible o puedes levantar el
   stack): ¿está Redis accesible?, ¿hay un proceso worker (dashboard-worker)
   realmente consumiendo la cola, o los jobs se quedan encolados sin que
   nadie los procese?

6. Cobertura de tests: busca los tests existentes que cubren estos
   ficheros (tests/unit/ y tests/integration/) y ejecútalos. Dime cuáles
   pasan, cuáles fallan, y qué partes de este flujo NO tienen ningún test
   (por ejemplo: ¿hay algún test que compruebe qué pasa cuando el scan
   falla?).

Al final, dame un resumen corto en formato de lista con: qué funciona de
verdad, qué está a medias, y qué está roto o sin implementar -- ordenado de
más a menos grave.
