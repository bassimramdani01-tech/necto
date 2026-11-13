#!/usr/bin/env python
"""Delete every run, event and registry row from the necto database.

Run it with the server environment (migrations stay applied):

    cd server && uv run python ../scripts/reset.py            # asks for confirmation
    cd server && uv run python ../scripts/reset.py --yes      # no prompt
    cd server && uv run python ../scripts/reset.py --yes --seed 6   # reset, then demo data
"""

from __future__ import annotations

import argparse
import sys

TABLES = ("events", "runs", "agents", "models")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        metavar="N",
        help="after resetting, insert N demo runs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        from sqlalchemy import text

        from necto_server.config import settings
        from necto_server.db import SessionLocal, engine
    except ImportError:
        print(
            "necto_server is not importable — run this from the server directory:\n"
            "  cd server && uv run python ../scripts/reset.py",
            file=sys.stderr,
        )
        return 2

    location = settings.database_url.rsplit("@", 1)[-1]
    with engine.connect() as conn:
        counts = {
            table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            for table in TABLES
        }

    print(f"database: {location}")
    print("to delete: " + ", ".join(f"{table}={count}" for table, count in counts.items()))

    if not args.yes:
        answer = input("Delete all runs and events? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("aborted")
            return 1

    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    print("reset complete")

    if args.seed > 0:
        from necto_server.services.demo import seed_demo_runs

        with SessionLocal() as db:
            run_ids = seed_demo_runs(db, count=args.seed)
        print(f"seeded {len(run_ids)} demo runs")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
