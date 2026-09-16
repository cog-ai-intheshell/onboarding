#!/usr/bin/env python3
"""Vérifie le parcours complet et supprime ses données temporaires."""

from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import psycopg


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


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


def request_json(base_url: str, path: str, method: str = "GET", payload=None, token: str = ""):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"{base_url}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        content = json.loads(error.read().decode("utf-8"))
        return error.code, content


def main() -> None:
    load_local_environment()
    base_url = os.environ.get("NXT_TEST_URL", "http://127.0.0.1:8767").rstrip("/")
    database_url = os.environ.get("DATABASE_URL")
    admin_password = os.environ.get("NXT_ADMIN_PASSWORD")
    if not database_url or not admin_password:
        raise SystemExit("DATABASE_URL et NXT_ADMIN_PASSWORD sont requis.")

    temporary_code = f"E2E-{secrets.token_hex(8).upper()}"
    generated_code = ""
    submission_id = ""
    sprint_slot_id = None

    try:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "INSERT INTO access_codes (code, active) VALUES (%s, TRUE)",
                (temporary_code,),
            )

        status, questions_payload = request_json(base_url, "/api/questions")
        assert status == 200 and questions_payload.get("questions"), "Les questions ne sont pas disponibles."
        questions = questions_payload["questions"]

        status, access_payload = request_json(
            base_url,
            "/api/validate-code",
            method="POST",
            payload={"code": temporary_code},
        )
        assert status == 200 and access_payload.get("accessToken"), "Le code temporaire n’est pas accepté."
        access_token = access_payload["accessToken"]

        test_profile = {
            "firstName": "Camille",
            "lastName": "Test",
            "phone": "+33 6 12 34 56 78",
            "email": "camille.test@example.com",
        }
        status, profile_payload = request_json(
            base_url,
            "/api/profile",
            method="POST",
            payload=test_profile,
            token=access_token,
        )
        assert status == 200 and profile_payload.get("profile") == test_profile, "L’enregistrement du profil a échoué."

        status, profile_payload = request_json(base_url, "/api/profile", token=access_token)
        assert status == 200 and profile_payload.get("profile") == test_profile, "Le profil restauré est incorrect."

        first_question = questions[0]["id"]
        draft_answers = {first_question: "Brouillon de vérification automatique."}
        status, _ = request_json(
            base_url,
            "/api/draft",
            method="POST",
            payload={"answers": draft_answers},
            token=access_token,
        )
        assert status == 200, "La sauvegarde du brouillon a échoué."

        status, draft_payload = request_json(base_url, "/api/draft", token=access_token)
        assert status == 200 and draft_payload.get("answers") == draft_answers, "Le brouillon restauré est incorrect."

        answers = {
            question["id"]: f"Réponse automatique pour la question {index + 1}."
            for index, question in enumerate(questions)
        }
        status, submission_payload = request_json(
            base_url,
            "/api/submissions",
            method="POST",
            payload={"answers": answers},
            token=access_token,
        )
        assert status == 201 and submission_payload.get("submissionId"), "L’envoi final a échoué."
        submission_id = submission_payload["submissionId"]

        status, admin_payload = request_json(
            base_url,
            "/api/admin/login",
            method="POST",
            payload={"password": admin_password},
        )
        assert status == 200 and admin_payload.get("adminToken"), "La connexion Admin a échoué."
        admin_token = admin_payload["adminToken"]

        status, created_slot_payload = request_json(
            base_url,
            "/api/admin/planning",
            method="POST",
            payload={"startDate": "2099-12-01"},
            token=admin_token,
        )
        assert status == 201 and created_slot_payload.get("slot", {}).get("id"), "La création d’un sprint a échoué."
        sprint_slot_id = created_slot_payload["slot"]["id"]

        status, planning_payload = request_json(base_url, "/api/planning", token=access_token)
        available_ids = {slot.get("id") for slot in planning_payload.get("slots", []) if not slot.get("taken")}
        assert status == 200 and sprint_slot_id in available_ids, "Le planning participant est incomplet."

        status, reservation_payload = request_json(
            base_url,
            "/api/planning/reserve",
            method="POST",
            payload={"slotId": sprint_slot_id, "startDate": "2099-12-01"},
            token=access_token,
        )
        assert status == 201 and reservation_payload.get("reserved"), "La réservation du sprint a échoué."

        status, admin_questions_payload = request_json(
            base_url,
            "/api/admin/questions",
            token=admin_token,
        )
        admin_questions = admin_questions_payload.get("questions", [])
        assert status == 200 and admin_questions == questions, "Les questions ne sont pas chargées dans l’Admin."

        status, saved_questions_payload = request_json(
            base_url,
            "/api/admin/questions",
            method="PUT",
            payload={"questions": admin_questions},
            token=admin_token,
        )
        assert status == 200 and saved_questions_payload.get("questions") == questions, "La sauvegarde des questions a échoué."

        status, codes_payload = request_json(
            base_url,
            "/api/admin/codes",
            token=admin_token,
        )
        listed_codes = {item.get("code") for item in codes_payload.get("codes", [])}
        assert status == 200 and temporary_code in listed_codes, "Le code temporaire n’apparaît pas dans l’Admin."

        status, generated_payload = request_json(
            base_url,
            "/api/admin/codes",
            method="POST",
            payload={"generate": True},
            token=admin_token,
        )
        generated_code = generated_payload.get("code", "")
        assert status == 201 and len(generated_code) == 6 and generated_code.isalpha(), "La génération de code a échoué."

        status, updated_payload = request_json(
            base_url,
            "/api/admin/codes",
            method="PATCH",
            payload={"code": generated_code, "active": False},
            token=admin_token,
        )
        assert status == 200 and updated_payload.get("active") is False, "La désactivation du code a échoué."

        status, responses_payload = request_json(
            base_url,
            "/api/admin/responses",
            token=admin_token,
        )
        submission_ids = {item.get("id") for item in responses_payload.get("submissions", [])}
        assert status == 200 and submission_id in submission_ids, "La soumission n’apparaît pas dans l’Admin."
        saved_submission = next(item for item in responses_payload["submissions"] if item.get("id") == submission_id)
        assert saved_submission.get("participant") == test_profile, "Le profil n’est pas associé à la réponse Admin."
        assert saved_submission.get("sprint", {}).get("id") == sprint_slot_id, "Le sprint n’est pas associé à la réponse Admin."

        status, slots_payload = request_json(base_url, "/api/admin/planning", token=admin_token)
        saved_slot = next((item for item in slots_payload.get("slots", []) if item.get("id") == sprint_slot_id), None)
        assert status == 200 and saved_slot and saved_slot.get("reservedBy") == temporary_code, "La réservation n’apparaît pas dans l’Admin."

        status, released_payload = request_json(
            base_url,
            "/api/admin/planning",
            method="PATCH",
            payload={"id": sprint_slot_id, "taken": False},
            token=admin_token,
        )
        released_slot = released_payload.get("slot", {})
        assert status == 200 and released_slot.get("taken") is False and not released_slot.get("reservedBy"), "La remise à disposition a échoué."

        print(f"Parcours vérifié : profil, questionnaire, planning, réservation et Admin opérationnels.")
    finally:
        with psycopg.connect(database_url) as connection:
            if sprint_slot_id:
                connection.execute("DELETE FROM sprint_slots WHERE id = %s", (sprint_slot_id,))
            if submission_id:
                connection.execute("DELETE FROM submissions WHERE id = %s", (submission_id,))
            if generated_code:
                connection.execute("DELETE FROM access_codes WHERE code = %s", (generated_code,))
            connection.execute("DELETE FROM drafts WHERE access_code = %s", (temporary_code,))
            connection.execute("DELETE FROM access_codes WHERE code = %s", (temporary_code,))


if __name__ == "__main__":
    main()
