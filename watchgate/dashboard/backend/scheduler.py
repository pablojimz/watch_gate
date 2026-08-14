"""Bucle ejecutor del scheduler de polling con lock distribuido en Redis."""

from __future__ import annotations

import logging
import time

from watchgate.dashboard.backend.tasks import get_redis_conn
from watchgate.service.repo_polling import RepoPollingService

logger = logging.getLogger(__name__)


def run_scheduler_loop(interval_seconds: int = 300) -> None:
    redis_conn = get_redis_conn()
    logger.info("Iniciando scheduler loop de WatchGate...")

    while True:
        try:
            # Lock distribuido por 120s para prevenir ejecuciones simultáneas entre réplicas
            with redis_conn.lock("watchgate:polling_lock", timeout=120, blocking_timeout=2):
                enqueued = RepoPollingService.poll_all_candidates()
                if enqueued > 0:
                    logger.info("Scheduler encoló %d PRs para auditoría.", enqueued)
        except Exception as exc:
            logger.warning("No se pudo adquirir lock o falló el barrido: %s", exc)

        time.sleep(interval_seconds)


if __name__ == "__main__":
    run_scheduler_loop()
