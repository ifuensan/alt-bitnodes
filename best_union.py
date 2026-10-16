"""Build the frozen BEST union (see queries/best_union.py). Run by hand:

    python best_union.py 2026-07-26            # refuses to overwrite
    python best_union.py 2026-07-26 --force

Not a timer: the result must not change once built, and the raw exports it
draws on are pruned after 90 days.
"""

import argparse
import datetime as dt
import json
import sys

from queries.best_union import write_best_union
from queries.config import BEST_NODES_FILE, BEST_STATS_FILE

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cutoff", type=dt.date.fromisoformat, help="last included UTC day, YYYY-MM-DD")
    ap.add_argument("--force", action="store_true", help="overwrite an existing frozen union")
    args = ap.parse_args()
    if (BEST_STATS_FILE.exists() or BEST_NODES_FILE.exists()) and not args.force:
        sys.exit(f"{BEST_STATS_FILE} exists; the BEST union is frozen. Use --force to rebuild.")
    result = write_best_union(args.cutoff)
    print(json.dumps({k: result[k] for k in
                      ("as_of", "snapshots", "sources", "ipv4", "ipv6", "tor", "i2p", "total")}))
