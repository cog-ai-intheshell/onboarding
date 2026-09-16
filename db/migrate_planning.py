#!/usr/bin/env python3
"""Ajoute uniquement le planning des sprints, sans lire les données participant locales."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[1]


def load_local_environment() -> None:
    env_file = ROOT / ".env.local"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def main() -> None:
    load_local_environment()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL manque dans .env.local.")

    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sprint_slots (
              id BIGSERIAL PRIMARY KEY,
              start_date DATE NOT NULL,
              taken BOOLEAN NOT NULL DEFAULT FALSE,
              access_code TEXT UNIQUE REFERENCES access_codes(code) ON DELETE SET NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              CONSTRAINT sprint_slots_reservation_state CHECK (access_code IS NULL OR taken = TRUE)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS sprint_slots_start_date_idx ON sprint_slots (start_date)"
        )
        slot_count = connection.execute("SELECT COUNT(*) FROM sprint_slots").fetchone()[0]
        if slot_count == 0:
            connection.execute(
                """
                INSERT INTO sprint_slots (start_date, taken)
                VALUES ('2026-10-03', FALSE),
                       ('2026-10-10', TRUE),
                       ('2026-10-18', FALSE),
                       ('2026-10-26', TRUE)
                """
            )

    print("Planning migré : table vérifiée et créneaux initiaux créés si nécessaire.")


if __name__ == "__main__":
    main()
