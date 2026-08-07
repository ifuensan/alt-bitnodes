"""Timer entrypoint: persist the crawler's latent datasets before they rotate.

Run every 10 minutes by alt-bitnodes-collector.timer. Two independent
sections — block propagation (binv:* zsets) and the daily services adoption
series. Each section runs under its own try/except so one failure never
starves the other (lesson from the 2026-07-22 cron-greenlet postmortem).

Exit code: 0 while at least one section succeeds (partial failures are
logged but degrade gracefully, so they must not mark the oneshot unit
failed on every tick). A total failure — both sections raised, i.e.
Redis down or the export dir broken — exits non-zero so systemd surfaces
it (`systemctl status`, `OnFailure=`).
"""

import json
import logging
import sys

from queries.block_propagation import collect_propagation
from queries.services import refresh_services_series


def run() -> dict:
    results: dict = {}
    failed: list[str] = []

    try:
        results["propagation"] = collect_propagation()
        logging.info("propagation: %s", results["propagation"])
    except Exception:
        logging.exception("propagation collection failed")
        results["propagation"] = None
        failed.append("propagation")

    try:
        series = refresh_services_series()
        results["services_days"] = len(series["days"])
        logging.info("services series: %d days", len(series["days"]))
    except Exception:
        logging.exception("services series refresh failed")
        results["services_days"] = None
        failed.append("services")

    results["failed"] = failed
    return results


SECTION_COUNT = 2


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    results = run()
    print(json.dumps(results))
    if len(results["failed"]) == SECTION_COUNT:
        logging.error("all %d collector sections failed", SECTION_COUNT)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
