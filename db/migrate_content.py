#!/usr/bin/env python3
"""Ajoute le contenu éditorial administrable sans lire les données participant."""

from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb


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
    content = json.loads((ROOT / "experience.json").read_text(encoding="utf-8"))

    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS site_content (
              key TEXT PRIMARY KEY,
              content JSONB NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        connection.execute(
            """
            INSERT INTO site_content (key, content)
            VALUES ('experience_page', %s)
            ON CONFLICT (key) DO NOTHING
            """,
            (Jsonb(content),),
        )

    print("Contenu éditorial migré sans lecture des données participant.")


if __name__ == "__main__":
    main()
