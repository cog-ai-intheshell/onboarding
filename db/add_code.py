#!/usr/bin/env python3
"""Ajoute ou réactive un code d’invitation dans Neon."""

from __future__ import annotations

import os
import sys
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
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        raise SystemExit('Usage : .venv/bin/python db/add_code.py "NOUVEAU-CODE"')

    load_local_environment()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL manque dans .env.local.")

    code = sys.argv[1].strip().upper()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO access_codes (code, active)
            VALUES (%s, TRUE)
            ON CONFLICT (code) DO UPDATE SET active = TRUE
            """,
            (code,),
        )
    print("Le code a été ajouté ou réactivé.")


if __name__ == "__main__":
    main()
