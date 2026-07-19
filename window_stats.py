"""Precompute the rolling-window unique-node counts and cache them to JSON.

Run hourly by alt-bitnodes-window-stats.timer. The union reads every snapshot
in the widest window, so it must not run in the API request path.
"""

import json
import logging
import sys

from queries.window_stats import write_window_stats

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = write_window_stats()
    logging.info("window stats: %s", [w for w in result.get("windows", [])])
    print(json.dumps(result))
    sys.exit(0)
