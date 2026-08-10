# Manual de Despliegue de Git Hooks Server-Side (`pre-receive`)

**WatchGate Git Server Hook Infrastructure**
**Ubicación**: `docs/manual_git_hooks.md`
**Fecha**: Agosto 2026

---

## 1. Introducción y Arquitectura

WatchGate proporciona un **Hook POSIX `pre-receive` Universal** (`watchgate/adapters/git_hook/pre_receive.py`) diseñado para ejecutarse en el servidor Git antes de aceptar cualquier `git push`. 

Este hook intercepta las propuestas de código en el servidor de control de versiones y consulta la **Engine API de WatchGate** o ejecuta el análisis local antes de que los commits se fusionen en la rama principal.

```
+------------------+         git push         +-------------------------------------+
|   Desarrollador  | -----------------------> |         Servidor Git / Bare         |
|   / Agente IA    |                          |  (GitLab, Bitbucket, Gitolite, SSH) |
+------------------+                          +------------------+------------------+
                                                                 |
                                                  Ejecuta hooks/pre-receive
                                                                 |
                                                                 v
                                              +-------------------------------------+
                                              | watchgate/adapters/git_hook/        |
                                              |           pre_receive.py            |
                                              +------------------+------------------+
                                                                 |
                                                  Petición HTTP / API (< 8s)
                                                                 |
                                                                 v
                                              +-------------------------------------+
                                              |       Engine API / WatchGate        |
                                              +------------------+------------------+
                                                                 |
                                                       Evalúa Semáforo
                                                                 |
                        +----------------------------------------+----------------------------------------+
                        |                                                                                 |
                 Semáforo VERDE / AMARILLO                                                          Semáforo ROJO
                        |                                                                                 |
                        v                                                                                 v
             [Exit Code 0: Push Aceptado]                                                  [Exit Code 1: Push Rechazado]
                                                                                           Imprime alertas en stderr
```

---

## 2. Características Clave del Hook `pre-receive`

1. **Soporte POSIX Estándar**: Ejecutable sin dependencias pesadas en el servidor Git.
2. **Manejo Explícito de SHA Nulo (`0000000000000000000000000000000000000000`)**:
   * En creaciones de ramas nuevas o puestas iniciales (`old-sha == 00*40`), extrae el diff utilizando `git diff-tree -p <new-sha>` en lugar de `git diff <old> <new>` para prevenir fallos catastróficos de Git.
   * En borrados de ramas (`new-sha == 00*40`), ignora la verificación y permite la operación de borrado inmediatamente.
3. **Control Estricto de Latencia (Timeout < 8s)**:
   * Aplica un timeout estricto de 8 segundos en la comunicación HTTP con la Engine API para evitar que la terminal del desarrollador se bloquee.
4. **Política de Contingencia Cero-Bloqueo o Fail-Closed**:
   * Ante caídas de red o errores de infraestructura de la API, aplica la política configurada por la organización (`fail_closed=True` o `fail_closed=False`).

---

## 3. Guía de Instalación por Entorno Git Server

### 3.1 Servidor Git Bare Estándar (SSH)

En un repositorio Git Bare en el servidor (`/srv/git/mi-proyecto.git`):

1. Copia el ejecutable del hook a la carpeta `hooks/`:

```bash
cp /ruta/a/watchgate/adapters/git_hook/pre_receive.py /srv/git/mi-proyecto.git/hooks/pre-receive
chmod +x /srv/git/mi-proyecto.git/hooks/pre-receive
```

2. Configura las variables de entorno para el hook en el servidor:

```bash
export WATCHGATE_API_URL="http://watchgate-engine.internal/api/v1/analyze"
export WATCHGATE_API_KEY="wg_live_4a8f9c2d..."
```

---

### 3.2 GitLab Self-Managed (Custom Hooks / Server Hooks)

En GitLab Self-Managed, los hooks de servidor se configuran como **Custom Hooks**:

1. Accede al directorio de almacenamiento del repositorio en el servidor GitLab (ej: `/var/opt/gitlab/git-data/repositories/@hashed/.../proyecto.git`).
2. Crea el directorio `custom_hooks`:

```bash
mkdir -p custom_hooks
```

3. Copia el hook `pre-receive`:

```bash
cp /ruta/a/watchgate/adapters/git_hook/pre_receive.py custom_hooks/pre-receive
chmod +x custom_hooks/pre-receive
chown -R git:git custom_hooks
```

---

### 3.3 Bitbucket Data Center / Server

En Atlassian Bitbucket Server:

1. Utiliza la funcionalidad **External Hooks Plugin** o instala el hook directamente en el directorio del repositorio en disco (`<BITBUCKET_HOME>/shared/data/repositories/<REPO_ID>/subhooks/pre-receive`).
2. Alternativamente, crea un script ejecutable wrapper en el sistema que invoque Python:

```bash
#!/bin/bash
export WATCHGATE_API_URL="http://watchgate.internal/api/v1/analyze"
export WATCHGATE_API_KEY="wg_live_..."
exec python3 /opt/watchgate/adapters/git_hook/pre_receive.py "$@"
```

---

### 3.4 Gitolite

En un servidor administrado con Gitolite:

1. Copia el hook al directorio de hooks comunes de Gitolite:

```bash
cp /ruta/a/watchgate/adapters/git_hook/pre_receive.py ~/.gitolite/hooks/common/pre-receive
chmod +x ~/.gitolite/hooks/common/pre-receive
gitolite setup --hooks
```

---

## 4. Pruebas de Funcionamiento

Para verificar el comportamiento del hook localmente sin realizar un push real, simula la entrada estándar enviando los parámetros de ref:

```bash
echo "4b825dc642cb6eb9a060e54bf8d69288fbee4904 e69de29bb2d1d6434b8b29ae775ad8c2e48c5391 refs/heads/main" | python3 watchgate/adapters/git_hook/pre_receive.py
```

Si el código contiene patrones de alto riesgo y `block_on_red: true`, el comando terminará con **Exit Code 1** imprimiendo las razones en `stderr`:

```
========================================================================
[BLOQUEADO POR WATCHGATE] Push rechazado por políticas de seguridad
========================================================================
Puntuación de Riesgo: 85/100 (Semáforo: ROJO)

Hallazgos Críticos:
  - [ESTÁTICA] eval-exec-dynamic: Uso peligroso de eval() detectado en src/auth.py
========================================================================
```
