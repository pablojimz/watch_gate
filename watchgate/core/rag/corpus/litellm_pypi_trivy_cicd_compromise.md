# Caso: litellm (PyPI) — compromiso vía Trivy en el propio pipeline de CI/CD

## Resumen

El 24 de marzo de 2026, la versión 1.82.8 de `litellm` (un proxy/SDK muy
usado para unificar el acceso a distintas APIs de LLM — Anthropic, OpenAI,
Gemini, modelos locales — bajo una interfaz común) se publicó en PyPI con
un fichero `.pth` malicioso (`litellm_init.pth`) que se ejecuta
automáticamente en cada arranque del intérprete Python siempre que
`litellm` esté instalado en el entorno. El grupo atacante (identificado
como "TeamPCP") no phisheó directamente al mantenedor de `litellm`: obtuvo
las credenciales de publicación a través de un compromiso **previo** de
Trivy, el escáner de seguridad open-source usado dentro del propio pipeline
de CI/CD de LiteLLM. Los administradores de PyPI pusieron en cuarentena el
paquete entero de emergencia, bloqueando todas las descargas nuevas.

## Vector de introducción

- Cadena de compromiso en dos pasos: Trivy (herramienta de terceros usada
  como dependencia de CI/CD, no como dependencia de la aplicación) fue
  comprometido primero; ese compromiso dio acceso a credenciales
  reutilizadas en el pipeline de CI/CD de `litellm`, que a su vez
  permitieron publicar en PyPI en nombre del mantenedor legítimo — sin que
  el mantenedor de `litellm` cometiera ningún error directo.
- Publicación en dos oleadas: la v1.82.7 escondía el payload en
  `proxy_server.py` (código de la propia aplicación); la v1.82.8, más
  agresiva, cambió a un fichero `.pth` — un mecanismo de Python pensado
  originalmente para añadir rutas al `sys.path`, pero que Python ejecuta
  automáticamente como código arbitrario en cuanto el intérprete arranca,
  **antes** de que el propio programa del usuario empiece a ejecutarse.
- El payload embebido estaba codificado en base64 dos veces seguidas
  (doble capa), reduciendo significativamente la visibilidad frente a
  análisis estático básico que solo decodifica un nivel.
- Objetivo de recolección amplio: credenciales de cualquier sistema capaz
  de almacenar credenciales o interactuar con servicios cloud, con especial
  atención a entornos Kubernetes (intentos de desplegar pods privilegiados
  y extraer secretos del clúster).

## Patrón a vigilar

Fichero nuevo con extensión `.pth` en un paquete Python (mecanismo de
ejecución automática al arrancar el intérprete, distinto y más silencioso
que `setup.py`/`postinstall`); contenido con múltiples capas de
codificación base64 anidada.

Técnica MITRE ATT&CK relacionada: T1195.001 (Compromise Software
Dependencies and Development Tools — vía compromiso de una herramienta de
CI/CD, no de una dependencia de aplicación), T1027 (Obfuscated Files or
Information), T1552 (Unsecured Credentials).
