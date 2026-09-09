"""Background worker entrypoint.

No jobs are registered yet — the ingestion pipeline (architecture/02
§2), Data Health recompute, Component Lifecycle (03 §6) and Attention
Engine scan (06 §3) jobs land in Sprints 3, 5, 8/18 and 21 respectively
per architecture/10-roadmap-and-acceptance.md. This process exists now so
`infra/docker-compose.yml` is runnable end-to-end from Sprint 1 onward;
it currently just idles and logs a heartbeat.
"""

import time

import structlog

logger = structlog.get_logger("datalume.worker")


def main() -> None:
    logger.info("worker.started", jobs_registered=0)
    while True:
        time.sleep(30)
        logger.info("worker.heartbeat")


if __name__ == "__main__":
    main()
