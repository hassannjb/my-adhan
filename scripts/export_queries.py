"""
Export the chat question log to CSV for analysis.

    python scripts/export_queries.py                        # remote questions -> stdout
    python scripts/export_queries.py --since 2026-10-01 -o questions.csv
    python scripts/export_queries.py --kind fallback        # what the bot couldn't answer
    python scripts/export_queries.py --include-local        # keep tests and local runs
"""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys

DEFAULT_DB = os.environ.get("QUERY_LOG_PATH") or os.path.expanduser("~/adhan-web/logs/queries.sqlite")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--since", help="UTC date or timestamp, inclusive (e.g. 2026-10-01)")
    ap.add_argument("--until", help="UTC date or timestamp, exclusive")
    ap.add_argument("--kind", help="only this reply kind: faq, times, convert, fallback, error")
    ap.add_argument("--include-local", action="store_true", help="include calls that did not come through Cloudflare")
    ap.add_argument("-o", "--out", help="CSV path (default: stdout)")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"no query log at {args.db}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    where, params = [], []
    if args.since:
        where.append("ts >= ?"); params.append(args.since)
    if args.until:
        where.append("ts < ?"); params.append(args.until)
    if args.kind:
        where.append("kind = ?"); params.append(args.kind)
    if not args.include_local:
        where.append("local = 0")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    cur = conn.execute(f"SELECT * FROM queries {clause} ORDER BY id", params)

    out = open(args.out, "w", newline="", encoding="utf-8") if args.out else sys.stdout
    w = csv.writer(out)
    w.writerow([d[0] for d in cur.description])
    n = 0
    for row in cur:
        w.writerow(row)
        n += 1
    if args.out:
        out.close()
        print(f"wrote {n} rows to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
