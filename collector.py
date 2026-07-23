"""Timer entrypoint: persist the crawler's latent datasets before they rotate.

Run every 10 minutes by alt-bitnodes-collector.timer. Three independent
sections — block propagation (binv:* zsets), the daily services adoption
series, and the 1/N unique-node estimate. Each section runs under its own
try/except so one failure never starves the others (lesson from the
2026-07-22 cron-greenlet postmortem).
"""

import json
import logging
import sys

from queries.block_propagation import collect_propagation
from queries.services import refresh_services_series
from queries.unique_nodes import write_unique_estimate


def run() -> dict:
    results: dict = {}

    try:
        results["propagation"] = collect_propagation()
        logging.info("propagation: %s", results["propagation"])
    except Exception:
        logging.exception("propagation collection failed")
        results["propagation"] = None

    try:
        series = refresh_services_series()
        results["services_days"] = len(series["days"])
        logging.info("services series: %d days", len(series["days"]))
    except Exception:
        logging.exception("services series refresh failed")
        results["services_days"] = None

    try:
        est = write_unique_estimate()
        results["unique_estimate"] = est["estimate"]
        logging.info("unique estimate: %s (reachable %s)",
                     est["estimate"], est["reachable"])
    except Exception:
        logging.exception("unique estimate failed")
        results["unique_estimate"] = None

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(run()))
    sys.exit(0)
