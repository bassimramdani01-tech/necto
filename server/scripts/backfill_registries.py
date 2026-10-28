"""Backfill the agents/models registries from events already in the database.

The registries are normally populated at ingest time; this rebuilds them for
data written before that behaviour existed. Safe to run repeatedly.

Usage (from the server/ directory):
    uv run python scripts/backfill_registries.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from necto_server.db import SessionLocal  # noqa: E402
from necto_server.models import Agent, Event, Model, Run  # noqa: E402
from necto_server.services import ingestion  # noqa: E402


def main() -> None:
    with SessionLocal() as db:
        run_ids = db.execute(select(Run.id)).scalars().all()
        if not run_ids:
            print("no runs found; nothing to backfill")
            return

        processed = 0
        for run_id in run_ids:
            events = (
                db.execute(select(Event).where(Event.run_id == run_id).order_by(Event.seq))
                .scalars()
                .all()
            )
            if not events:
                continue
            ingestion.register_registries(db, list(events))
            db.commit()
            processed += len(events)

        agents = db.execute(select(func.count()).select_from(Agent)).scalar()
        models = db.execute(select(func.count()).select_from(Model)).scalar()
        print(f"backfilled {processed} events -> {agents} agents, {models} models")


if __name__ == "__main__":
    main()
