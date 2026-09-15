#!/usr/bin/env python3
"""Crée le schéma Neon et importe les données JSON locales sans afficher de secrets."""

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


def read_json(name: str, fallback):
    try:
        return json.loads((ROOT / name).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def normalized_codes() -> set[str]:
    data = read_json("access_codes.json", {"codes": []})
    entries = data.get("codes", []) if isinstance(data, dict) else []
    codes = set()
    for entry in entries:
        value = entry.get("code", "") if isinstance(entry, dict) else entry
        if isinstance(value, str) and value.strip():
            codes.add(value.strip().upper())
    return codes


def main() -> None:
    load_local_environment()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL manque dans .env.local.")

    schema = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    drafts = read_json("drafts.json", {})
    submissions = read_json("responses.json", [])
    codes = normalized_codes()

    if isinstance(drafts, dict):
        codes.update(str(code).strip().upper() for code in drafts if str(code).strip())
    if isinstance(submissions, list):
        codes.update(
            str(item.get("accessCode", "")).strip().upper()
            for item in submissions
            if isinstance(item, dict) and str(item.get("accessCode", "")).strip()
        )

    imported_drafts = 0
    imported_submissions = 0
    with psycopg.connect(database_url) as connection:
        connection.execute(schema)

        for code in sorted(codes):
            connection.execute(
                """
                INSERT INTO access_codes (code, active)
                VALUES (%s, TRUE)
                ON CONFLICT (code) DO UPDATE SET active = TRUE
                """,
                (code,),
            )

        if isinstance(drafts, dict):
            for raw_code, draft in drafts.items():
                code = str(raw_code).strip().upper()
                if not code or not isinstance(draft, dict):
                    continue
                answers = draft.get("answers", {})
                if not isinstance(answers, dict):
                    continue
                connection.execute(
                    """
                    INSERT INTO drafts (access_code, answers, saved_at)
                    VALUES (%s, %s, COALESCE(%s::timestamptz, NOW()))
                    ON CONFLICT (access_code)
                    DO UPDATE SET answers = EXCLUDED.answers, saved_at = EXCLUDED.saved_at
                    """,
                    (code, Jsonb(answers), draft.get("savedAt")),
                )
                imported_drafts += 1

        if isinstance(submissions, list):
            for submission in submissions:
                if not isinstance(submission, dict):
                    continue
                submission_id = str(submission.get("id", "")).strip()
                code = str(submission.get("accessCode", "")).strip().upper()
                questions = submission.get("questions", [])
                answers = submission.get("answers", {})
                if not submission_id or not code or not isinstance(questions, list) or not isinstance(answers, dict):
                    continue
                result = connection.execute(
                    """
                    INSERT INTO submissions (id, access_code, questions, answers, submitted_at)
                    VALUES (%s, %s, %s, %s, COALESCE(%s::timestamptz, NOW()))
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (submission_id, code, Jsonb(questions), Jsonb(answers), submission.get("submittedAt")),
                )
                imported_submissions += max(result.rowcount, 0)

    print(f"Migration terminée : {len(codes)} code(s), {imported_drafts} brouillon(s), {imported_submissions} soumission(s) importée(s).")


if __name__ == "__main__":
    main()
