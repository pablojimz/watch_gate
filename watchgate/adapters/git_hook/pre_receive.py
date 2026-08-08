"""Adaptador POSIX universal para Hook de servidor Git `pre-receive`.

Intercepta comandos `git push` en servidores Git corporativos (GitLab, Bitbucket,
Gitolite, Gerrit, repos Bare SSH) antes de fusionar código a producción.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import Any

from watchgate.config import load_config
from watchgate.core.diffparser import parse_diff_from_text
from watchgate.core.models import Semaforo
from watchgate.core.pipeline import run_full_analysis

NULL_SHA = "0000000000000000000000000000000000000000"
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
DEFAULT_TIMEOUT_SECONDS = 8.0


class PreReceiveTimeout(Exception):
    """Se superó `timeout_seconds` analizando un ref -- ver `run_pre_receive`."""


def extract_diff_from_shas(
    old_sha: str, new_sha: str, repo_path: str = ".", timeout: float | None = None
) -> str:
    """Extrae el parche unificado git diff entre dos referencias, manejando el SHA nulo.

    Si `old_sha` es `00*40` (push inicial de repositorio o creación de rama/tag),
    compara contra el árbol vacío de Git (`4b825dc...`) para extraer el diff completo.

    Los fallos (git falla, timeout, el diff no se puede decodificar como
    texto) se PROPAGAN -- antes se atrapaban con un `except Exception`
    genérico que devolvía `""`, y el llamador trataba cadena vacía igual
    que "sin cambios que analizar", dejando pasar el push SIN analizar
    (fail-open) justo en el punto donde un hook `pre-receive` debe ser
    fail-closed. Ahora el llamador es quien decide qué hacer con el fallo
    (política `fail_closed`), no esta función en silencio.
    """
    if old_sha.replace("0", "") == "":
        base_ref = EMPTY_TREE_SHA
    else:
        base_ref = old_sha

    if new_sha.replace("0", "") == "":
        return ""

    cmd = ["git", "diff", f"{base_ref}..{new_sha}"]
    proc = subprocess.run(
        cmd, cwd=repo_path, capture_output=True, text=True, check=True, timeout=timeout
    )
    return proc.stdout


def parse_pre_receive_input(stdin_text: str) -> list[tuple[str, str, str]]:
    """Parsea las líneas enviadas por Git a `stdin` con formato `<old_sha> <new_sha> <ref_name>`."""
    refs: list[tuple[str, str, str]] = []
    for line in stdin_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 3:
            refs.append((parts[0], parts[1], parts[2]))
    return refs


def run_pre_receive(
    stdin_text: str | None = None,
    repo_path: str = ".",
    api_url: str | None = None,
    api_key: str | None = None,
    fail_closed: bool = True,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> int:
    """Ejecuta la lógica del hook pre-receive.

    Lee `stdin`, extrae los diffs, ejecuta la evaluación de riesgo de WatchGate
    y rechaza el push (retornando exit 1) si el semáforo es ROJO y la política exige bloqueo.

    `api_url`/`api_key` se aceptan para una futura delegación a un Engine
    API central (gobernanza/cuota compartida entre varios servidores Git),
    pero TODAVÍA NO ESTÁ IMPLEMENTADA -- el análisis siempre corre en local,
    con la config `.watchgate.yml` de este repo únicamente. Se avisa en vez
    de aceptarlos en silencio para que un administrador que los configure
    esperando supervisión centralizada no asuma que la tiene.
    """
    if api_url or api_key:
        sys.stderr.write(
            "[WatchGate pre-receive] AVISO: WATCHGATE_SERVER_URL/WATCHGATE_API_KEY están "
            "configurados pero la delegación a un Engine API central todavía no está "
            "implementada en este hook -- el análisis se ejecuta en LOCAL, sin la "
            "gobernanza/cuota centralizada que esa configuración sugiere.\n"
        )

    if stdin_text is None:
        stdin_text = sys.stdin.read()

    ref_tuples = parse_pre_receive_input(stdin_text)
    if not ref_tuples:
        sys.stderr.write("[WatchGate pre-receive] No se recibieron referencias en stdin.\n")
        return 0

    overall_blocked = False
    config = load_config()
    # SIGALRM (POSIX -- ver docstring del módulo) es lo único que puede
    # interrumpir de verdad `run_full_analysis` si se cuelga (p. ej. la
    # capa semántica esperando una respuesta del LLM que nunca llega):
    # `timeout_seconds` se aceptaba como parámetro pero nunca se usaba en
    # ningún sitio, así que un `git diff`/análisis colgado bloqueaba
    # `git push` INDEFINIDAMENTE para cualquier cliente del servidor Git
    # -- un DoS trivial sobre el flujo de push corporativo. Con la alarma,
    # el timeout se aplica al ref completo (extracción de diff + análisis)
    # y, al expirar, se trata igual que cualquier otro fallo de la política
    # `fail_closed` de abajo.
    supports_alarm = hasattr(signal, "SIGALRM")
    if not supports_alarm:
        sys.stderr.write(
            "[WatchGate pre-receive] signal.SIGALRM no disponible en esta plataforma -- "
            "el timeout no puede aplicarse a un análisis colgado (solo al propio `git diff`).\n"
        )

    def _on_alarm(signum: int, frame: Any) -> None:  # noqa: ARG001
        raise PreReceiveTimeout(f"Timeout de {timeout_seconds}s excedido")

    for old_sha, new_sha, ref_name in ref_tuples:
        if new_sha.replace("0", "") == "":
            # Eliminación de rama o tag: no requiere análisis de código
            continue

        metadata: dict[str, Any] = {
            "ref_name": ref_name,
            "repo": repo_path,
            "pr_id": ref_name.split("/")[-1],
        }

        previous_handler = None
        if supports_alarm:
            previous_handler = signal.signal(signal.SIGALRM, _on_alarm)
            signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        try:
            diff_text = extract_diff_from_shas(
                old_sha, new_sha, repo_path=repo_path, timeout=timeout_seconds
            )
            if not diff_text.strip():
                continue

            diff = parse_diff_from_text(
                diff_text=diff_text,
                base_sha=old_sha if old_sha.replace("0", "") != "" else EMPTY_TREE_SHA,
                head_sha=new_sha,
                repo_path=repo_path,
            )
            result = run_full_analysis(diff=diff, metadata=metadata, config=config)
        except Exception as err:
            sys.stderr.write(
                f"[WatchGate pre-receive] Error durante el análisis de {ref_name}: {err}\n"
            )
            if fail_closed:
                sys.stderr.write(
                    "[WatchGate pre-receive] Política FAIL_CLOSED activa: "
                    "Push rechazado por fallo de infraestructura.\n"
                )
                return 1
            continue
        finally:
            if supports_alarm:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous_handler)

        if result.semaforo == Semaforo.ROJO and config.block_on_red:
            overall_blocked = True
            sys.stderr.write(f"\n❌ [WatchGate] PUSH RECHAZADO EN SERVIDOR GIT ({ref_name})\n")
            sys.stderr.write(f"   Puntuación de riesgo: {result.score}/100 [SEMÁFORO ROJO]\n")
            for layer_name, layer_res in result.layer_results.items():
                if not layer_res.skipped and layer_res.risk_score >= config.thresholds.get(
                    "red", 70
                ):
                    sys.stderr.write(f"   - {layer_name.upper()}: {layer_res.justification}\n")
            sys.stderr.write(
                "   Corrija los hallazgos de seguridad antes de reintentar el git push.\n\n"
            )
        else:
            sys.stderr.write(
                f"✅ [WatchGate] PUSH APROBADO ({ref_name}): "
                f"{result.semaforo.value.upper()} ({result.score}/100)\n"
            )

    return 1 if overall_blocked else 0


def main() -> int:
    """Punto de entrada ejecutable para el hook POSIX `.git/hooks/pre-receive`."""
    fail_closed_env = os.environ.get("WATCHGATE_FAIL_CLOSED", "true").lower() in (
        "true",
        "1",
        "yes",
    )
    try:
        timeout_env = float(os.environ.get("WATCHGATE_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)))
    except ValueError:
        timeout_env = DEFAULT_TIMEOUT_SECONDS

    return run_pre_receive(
        stdin_text=sys.stdin.read(),
        repo_path=".",
        api_url=os.environ.get("WATCHGATE_SERVER_URL"),
        api_key=os.environ.get("WATCHGATE_API_KEY"),
        fail_closed=fail_closed_env,
        timeout_seconds=timeout_env,
    )


if __name__ == "__main__":
    sys.exit(main())
