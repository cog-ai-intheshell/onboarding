"""API serverless Vercel pour l’onboarding NXT."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from datetime import date, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")
NEW_ACCESS_CODE_PATTERN = re.compile(r"^[A-Z]{1,6}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PATTERN = re.compile(r"^[0-9+().\s-]{6,30}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ACCESS_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"
MAX_BODY_SIZE = 2_000_000


class ConfigurationError(RuntimeError):
    """La configuration du service est absente ou invalide."""


def get_questions() -> list[dict]:
    with database_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, title, helper, placeholder, required
            FROM questionnaire_questions
            ORDER BY position ASC
            """
        ).fetchall()
    return [{
        "id": row["id"],
        "title": row["title"],
        "helper": row["helper"],
        "placeholder": row["placeholder"],
        "required": row["required"],
    } for row in rows]


def database_connection():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ConfigurationError("DATABASE_URL est absente.")
    return psycopg.connect(database_url, row_factory=dict_row)


def server_secret() -> bytes:
    value = os.environ.get("NXT_SERVER_SECRET")
    if not value or len(value) < 32:
        raise ConfigurationError("NXT_SERVER_SECRET est absente ou trop courte.")
    return value.encode("utf-8")


def code_is_active(code: str) -> bool:
    with database_connection() as connection:
        row = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM access_codes WHERE code = %s AND active = TRUE) AS allowed",
            (code,),
        ).fetchone()
    return bool(row and row["allowed"])


def create_access_token(code: str) -> str:
    expires_at = int(time.time()) + 4 * 60 * 60
    payload = f"{code}|{expires_at}"
    signature = hmac.new(server_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}|{signature}"


def verify_access_token(token: str) -> str | None:
    try:
        code, expires_at, signature = token.split("|", 2)
        payload = f"{code}|{expires_at}"
        expected = hmac.new(server_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected) or int(expires_at) < time.time():
            return None
        return code if code_is_active(code) else None
    except (ValueError, TypeError):
        return None


def verify_admin_password(password: str) -> bool:
    configured_password = os.environ.get("NXT_ADMIN_PASSWORD")
    if not configured_password:
        raise ConfigurationError("NXT_ADMIN_PASSWORD est absente.")
    return hmac.compare_digest(password, configured_password)


def create_admin_token() -> str:
    expires_at = int(time.time()) + 2 * 60 * 60
    payload = f"admin|{expires_at}"
    signature = hmac.new(server_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}|{signature}"


def verify_admin_token(token: str) -> bool:
    try:
        role, expires_at, signature = token.split("|", 2)
        payload = f"{role}|{expires_at}"
        expected = hmac.new(server_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return role == "admin" and int(expires_at) >= time.time() and hmac.compare_digest(signature, expected)
    except (ValueError, TypeError):
        return False


def parse_iso_date(value) -> date | None:
    if not isinstance(value, str) or not DATE_PATTERN.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def ranges_overlap(first_start: date, second_start: date) -> bool:
    first_end = first_start + timedelta(days=4)
    second_end = second_start + timedelta(days=4)
    return first_start <= second_end and first_end >= second_start


class handler(BaseHTTPRequestHandler):
    """Point d’entrée unique vers lequel les routes API sont réécrites."""

    server_version = "NXTOnboarding/2.0"

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        super().end_headers()

    def do_GET(self):
        try:
            route = self.requested_route()
            if route == "questions":
                self.get_questions_route()
            elif route == "profile":
                self.get_profile()
            elif route == "draft":
                self.get_draft()
            elif route == "planning":
                self.get_planning()
            elif route == "admin-responses":
                self.get_admin_responses()
            elif route == "admin-codes":
                self.get_admin_codes()
            elif route == "admin-questions":
                self.get_admin_questions()
            elif route == "admin-planning":
                self.get_admin_planning()
            else:
                self.send_json({"message": "Route introuvable."}, HTTPStatus.NOT_FOUND)
        except Exception as error:  # La réponse reste neutre, le détail part dans les logs Vercel.
            self.handle_server_error(error)

    def do_POST(self):
        try:
            route = self.requested_route()
            if route == "validate-code":
                self.validate_code()
            elif route == "profile":
                self.save_profile()
            elif route == "admin-login":
                self.admin_login()
            elif route == "admin-codes":
                self.create_admin_code()
            elif route == "draft":
                self.save_draft()
            elif route == "submissions":
                self.save_submission()
            elif route == "planning-reserve":
                self.reserve_planning_slot()
            elif route == "admin-planning":
                self.create_admin_planning_slot()
            else:
                self.send_json({"message": "Route introuvable."}, HTTPStatus.NOT_FOUND)
        except Exception as error:  # La réponse reste neutre, le détail part dans les logs Vercel.
            self.handle_server_error(error)

    def do_PATCH(self):
        try:
            if self.requested_route() == "admin-codes":
                self.update_admin_code()
            elif self.requested_route() == "admin-planning":
                self.update_admin_planning_slot()
            else:
                self.send_json({"message": "Route introuvable."}, HTTPStatus.NOT_FOUND)
        except Exception as error:
            self.handle_server_error(error)

    def do_DELETE(self):
        try:
            if self.requested_route() == "admin-planning":
                self.delete_admin_planning_slot()
            else:
                self.send_json({"message": "Route introuvable."}, HTTPStatus.NOT_FOUND)
        except Exception as error:
            self.handle_server_error(error)

    def do_PUT(self):
        try:
            if self.requested_route() == "admin-questions":
                self.save_admin_questions()
            else:
                self.send_json({"message": "Route introuvable."}, HTTPStatus.NOT_FOUND)
        except Exception as error:
            self.handle_server_error(error)

    def requested_route(self) -> str:
        parsed = urlparse(self.path)
        query_route = parse_qs(parsed.query).get("route", [""])[0]
        if query_route:
            return query_route
        return parsed.path.removeprefix("/api/").replace("admin/", "admin-")

    def read_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY_SIZE:
                return None
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    def bearer_token(self) -> str:
        authorization = self.headers.get("Authorization", "")
        return authorization.removeprefix("Bearer ").strip()

    def authenticated_code(self) -> str | None:
        return verify_access_token(self.bearer_token())

    def authenticated_admin(self) -> bool:
        return verify_admin_token(self.bearer_token())

    def get_questions_route(self):
        questions = get_questions()
        if not questions:
            self.send_json({"message": "Aucune question valide n’est configurée."}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        self.send_json({"questions": questions})

    def validate_code(self):
        body = self.read_body()
        code = body.get("code", "").strip().upper() if isinstance(body, dict) else ""
        if not code or not code_is_active(code):
            self.send_json(
                {"valid": False, "message": "Ce code n’est pas reconnu. Vérifie-le et réessaie."},
                HTTPStatus.UNAUTHORIZED,
            )
            return
        self.send_json({"valid": True, "accessToken": create_access_token(code)})

    def admin_login(self):
        body = self.read_body()
        password = body.get("password", "") if isinstance(body, dict) else ""
        if not isinstance(password, str) or not verify_admin_password(password):
            self.send_json({"message": "Mot de passe incorrect."}, HTTPStatus.UNAUTHORIZED)
            return
        self.send_json({"authenticated": True, "adminToken": create_admin_token()})

    def get_admin_responses(self):
        if not self.authenticated_admin():
            self.send_json({"message": "Session administrateur invalide ou expirée."}, HTTPStatus.UNAUTHORIZED)
            return

        with database_connection() as connection:
            rows = connection.execute(
                """
                SELECT submissions.id, submissions.submitted_at, submissions.access_code,
                       submissions.questions, submissions.answers,
                       participants.first_name, participants.last_name,
                       participants.phone, participants.email,
                       sprint_slots.id AS sprint_slot_id,
                       sprint_slots.start_date AS sprint_start_date
                FROM submissions
                LEFT JOIN participants ON participants.access_code = submissions.access_code
                LEFT JOIN sprint_slots ON sprint_slots.access_code = submissions.access_code
                ORDER BY submissions.submitted_at DESC
                """
            ).fetchall()

        submissions = [{
            "id": row["id"],
            "submittedAt": row["submitted_at"].isoformat(),
            "accessCode": row["access_code"],
            "questions": row["questions"],
            "answers": row["answers"],
            "participant": {
                "firstName": row["first_name"],
                "lastName": row["last_name"],
                "phone": row["phone"],
                "email": row["email"],
            } if row["first_name"] is not None else None,
            "sprint": {
                "id": row["sprint_slot_id"],
                "startDate": row["sprint_start_date"].isoformat(),
                "endDate": (row["sprint_start_date"] + timedelta(days=4)).isoformat(),
            } if row["sprint_slot_id"] is not None else None,
        } for row in rows]
        self.send_json({"submissions": submissions, "count": len(submissions)})

    def get_profile(self):
        code = self.authenticated_code()
        if not code:
            self.send_json({"message": "Ta session a expiré."}, HTTPStatus.UNAUTHORIZED)
            return

        with database_connection() as connection:
            row = connection.execute(
                "SELECT first_name, last_name, phone, email FROM participants WHERE access_code = %s",
                (code,),
            ).fetchone()
        profile = {
            "firstName": row["first_name"],
            "lastName": row["last_name"],
            "phone": row["phone"],
            "email": row["email"],
        } if row else None
        self.send_json({"profile": profile})

    def save_profile(self):
        code = self.authenticated_code()
        if not code:
            self.send_json({"message": "Ta session a expiré."}, HTTPStatus.UNAUTHORIZED)
            return

        body = self.read_body()
        if not isinstance(body, dict):
            self.send_json({"message": "Les informations envoyées sont invalides."}, HTTPStatus.BAD_REQUEST)
            return

        fields = {
            "firstName": body.get("firstName", ""),
            "lastName": body.get("lastName", ""),
            "phone": body.get("phone", ""),
            "email": body.get("email", ""),
        }
        if not all(isinstance(value, str) for value in fields.values()):
            self.send_json({"message": "Les informations envoyées sont invalides."}, HTTPStatus.BAD_REQUEST)
            return

        profile = {key: value.strip() for key, value in fields.items()}
        if not profile["firstName"] or len(profile["firstName"]) > 100:
            self.send_json({"message": "Renseigne un prénom valide."}, HTTPStatus.BAD_REQUEST)
            return
        if not profile["lastName"] or len(profile["lastName"]) > 100:
            self.send_json({"message": "Renseigne un nom valide."}, HTTPStatus.BAD_REQUEST)
            return
        if not PHONE_PATTERN.fullmatch(profile["phone"]):
            self.send_json({"message": "Renseigne un numéro de téléphone valide."}, HTTPStatus.BAD_REQUEST)
            return
        profile["email"] = profile["email"].lower()
        if len(profile["email"]) > 254 or not EMAIL_PATTERN.fullmatch(profile["email"]):
            self.send_json({"message": "Renseigne une adresse email valide."}, HTTPStatus.BAD_REQUEST)
            return

        with database_connection() as connection:
            connection.execute(
                """
                INSERT INTO participants (access_code, first_name, last_name, phone, email, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (access_code)
                DO UPDATE SET first_name = EXCLUDED.first_name,
                              last_name = EXCLUDED.last_name,
                              phone = EXCLUDED.phone,
                              email = EXCLUDED.email,
                              updated_at = NOW()
                """,
                (code, profile["firstName"], profile["lastName"], profile["phone"], profile["email"]),
            )
        self.send_json({"saved": True, "profile": profile})

    def get_admin_codes(self):
        if not self.authenticated_admin():
            self.send_json({"message": "Session administrateur invalide ou expirée."}, HTTPStatus.UNAUTHORIZED)
            return

        with database_connection() as connection:
            rows = connection.execute(
                """
                SELECT access_codes.code, access_codes.active, access_codes.created_at,
                       COUNT(submissions.id)::int AS submission_count
                FROM access_codes
                LEFT JOIN submissions ON submissions.access_code = access_codes.code
                GROUP BY access_codes.code, access_codes.active, access_codes.created_at
                ORDER BY access_codes.created_at DESC, access_codes.code ASC
                """
            ).fetchall()

        codes = [{
            "code": row["code"],
            "active": row["active"],
            "createdAt": row["created_at"].isoformat(),
            "submissionCount": row["submission_count"],
        } for row in rows]
        self.send_json({"codes": codes, "count": len(codes)})

    def get_admin_questions(self):
        if not self.authenticated_admin():
            self.send_json({"message": "Session administrateur invalide ou expirée."}, HTTPStatus.UNAUTHORIZED)
            return
        questions = get_questions()
        self.send_json({"questions": questions, "count": len(questions)})

    def save_admin_questions(self):
        if not self.authenticated_admin():
            self.send_json({"message": "Session administrateur invalide ou expirée."}, HTTPStatus.UNAUTHORIZED)
            return

        body = self.read_body()
        entries = body.get("questions") if isinstance(body, dict) else None
        if not isinstance(entries, list) or not 1 <= len(entries) <= 50:
            self.send_json({"message": "Le questionnaire doit contenir entre 1 et 50 questions."}, HTTPStatus.BAD_REQUEST)
            return

        questions = []
        seen_ids = set()
        for entry in entries:
            if not isinstance(entry, dict):
                self.send_json({"message": "Une question est invalide."}, HTTPStatus.BAD_REQUEST)
                return

            question_id = entry.get("id", "")
            if not isinstance(question_id, str) or not ID_PATTERN.fullmatch(question_id):
                question_id = f"q_{secrets.token_hex(6)}"
            if question_id in seen_ids:
                self.send_json({"message": "Deux questions possèdent le même identifiant."}, HTTPStatus.BAD_REQUEST)
                return

            title = entry.get("title", "")
            helper = entry.get("helper", "")
            placeholder = entry.get("placeholder", "Ta réponse…")
            required = entry.get("required", True)
            if not isinstance(title, str) or not title.strip() or len(title.strip()) > 300:
                self.send_json({"message": "Chaque question doit avoir un titre valide."}, HTTPStatus.BAD_REQUEST)
                return
            if not isinstance(helper, str) or len(helper.strip()) > 5_000:
                self.send_json({"message": "Une explication de question est trop longue."}, HTTPStatus.BAD_REQUEST)
                return
            if not isinstance(placeholder, str) or len(placeholder.strip()) > 300:
                self.send_json({"message": "Un texte indicatif est trop long."}, HTTPStatus.BAD_REQUEST)
                return
            if not isinstance(required, bool):
                self.send_json({"message": "Le statut obligatoire d’une question est invalide."}, HTTPStatus.BAD_REQUEST)
                return

            seen_ids.add(question_id)
            questions.append({
                "id": question_id,
                "title": title.strip(),
                "helper": helper.strip(),
                "placeholder": placeholder.strip() or "Ta réponse…",
                "required": required,
            })

        with database_connection() as connection:
            connection.execute("DELETE FROM questionnaire_questions")
            for position, question in enumerate(questions, start=1):
                connection.execute(
                    """
                    INSERT INTO questionnaire_questions (id, title, helper, placeholder, required, position, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (
                        question["id"], question["title"], question["helper"],
                        question["placeholder"], question["required"], position,
                    ),
                )

        self.send_json({"saved": True, "questions": questions, "count": len(questions)})

    def create_admin_code(self):
        if not self.authenticated_admin():
            self.send_json({"message": "Session administrateur invalide ou expirée."}, HTTPStatus.UNAUTHORIZED)
            return

        body = self.read_body()
        if not isinstance(body, dict):
            self.send_json({"message": "La demande est invalide."}, HTTPStatus.BAD_REQUEST)
            return

        generate = body.get("generate") is True
        requested_code = body.get("code", "")
        if not generate:
            code = requested_code.strip().upper() if isinstance(requested_code, str) else ""
            if not NEW_ACCESS_CODE_PATTERN.fullmatch(code):
                self.send_json(
                    {"message": "Le code doit contenir entre 1 et 6 lettres, sans chiffre ni symbole."},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            if not self.insert_access_code(code):
                self.send_json({"message": "Ce code existe déjà."}, HTTPStatus.CONFLICT)
                return
        else:
            code = ""
            for _ in range(20):
                candidate = "".join(secrets.choice(ACCESS_CODE_ALPHABET) for _ in range(6))
                if self.insert_access_code(candidate):
                    code = candidate
                    break
            if not code:
                self.send_json({"message": "Impossible de générer un code pour le moment."}, HTTPStatus.CONFLICT)
                return

        self.send_json({"created": True, "code": code, "active": True}, HTTPStatus.CREATED)

    def insert_access_code(self, code: str) -> bool:
        with database_connection() as connection:
            row = connection.execute(
                """
                INSERT INTO access_codes (code, active)
                VALUES (%s, TRUE)
                ON CONFLICT (code) DO NOTHING
                RETURNING code
                """,
                (code,),
            ).fetchone()
        return row is not None

    def update_admin_code(self):
        if not self.authenticated_admin():
            self.send_json({"message": "Session administrateur invalide ou expirée."}, HTTPStatus.UNAUTHORIZED)
            return

        body = self.read_body()
        code = body.get("code", "").strip().upper() if isinstance(body, dict) and isinstance(body.get("code"), str) else ""
        active = body.get("active") if isinstance(body, dict) else None
        if not code or len(code) > 80 or not isinstance(active, bool):
            self.send_json({"message": "La modification demandée est invalide."}, HTTPStatus.BAD_REQUEST)
            return

        with database_connection() as connection:
            row = connection.execute(
                "UPDATE access_codes SET active = %s WHERE code = %s RETURNING code, active",
                (active, code),
            ).fetchone()
        if not row:
            self.send_json({"message": "Ce code est introuvable."}, HTTPStatus.NOT_FOUND)
            return
        self.send_json({"updated": True, "code": row["code"], "active": row["active"]})

    def planning_rows(self, connection):
        return connection.execute(
            """
            SELECT sprint_slots.id, sprint_slots.start_date, sprint_slots.taken,
                   sprint_slots.access_code, participants.first_name, participants.last_name
            FROM sprint_slots
            LEFT JOIN participants ON participants.access_code = sprint_slots.access_code
            ORDER BY sprint_slots.start_date ASC, sprint_slots.id ASC
            """
        ).fetchall()

    def serialize_planning_slot(self, row, include_identity=False, current_code=None):
        payload = {
            "id": row["id"],
            "startDate": row["start_date"].isoformat(),
            "endDate": (row["start_date"] + timedelta(days=4)).isoformat(),
            "taken": row["taken"],
            "mine": bool(current_code and row["access_code"] == current_code),
        }
        if include_identity:
            participant_name = " ".join(
                value for value in (row["first_name"], row["last_name"]) if value
            )
            payload["reservedBy"] = row["access_code"]
            payload["participantName"] = participant_name or None
        return payload

    def get_planning(self):
        code = self.authenticated_code()
        if not code:
            self.send_json({"message": "Ta session a expiré."}, HTTPStatus.UNAUTHORIZED)
            return

        with database_connection() as connection:
            submitted = connection.execute(
                "SELECT EXISTS (SELECT 1 FROM submissions WHERE access_code = %s) AS complete",
                (code,),
            ).fetchone()["complete"]
            if not submitted:
                self.send_json({"message": "Complète d’abord le questionnaire."}, HTTPStatus.FORBIDDEN)
                return
            rows = self.planning_rows(connection)
        slots = [self.serialize_planning_slot(row, current_code=code) for row in rows]
        reservation = next((slot for slot in slots if slot["mine"]), None)
        self.send_json({"slots": slots, "reservation": reservation})

    def reserve_planning_slot(self):
        code = self.authenticated_code()
        if not code:
            self.send_json({"message": "Ta session a expiré."}, HTTPStatus.UNAUTHORIZED)
            return

        body = self.read_body()
        slot_id = body.get("slotId") if isinstance(body, dict) else None
        start_date = parse_iso_date(body.get("startDate")) if isinstance(body, dict) else None
        if not isinstance(slot_id, int) or not start_date:
            self.send_json({"message": "La période sélectionnée est invalide."}, HTTPStatus.BAD_REQUEST)
            return

        with database_connection() as connection:
            connection.execute("LOCK TABLE sprint_slots IN SHARE ROW EXCLUSIVE MODE")
            submitted = connection.execute(
                "SELECT EXISTS (SELECT 1 FROM submissions WHERE access_code = %s) AS complete",
                (code,),
            ).fetchone()["complete"]
            if not submitted:
                self.send_json({"message": "Complète d’abord le questionnaire."}, HTTPStatus.FORBIDDEN)
                return

            existing = connection.execute(
                "SELECT id, start_date, taken, access_code FROM sprint_slots WHERE access_code = %s",
                (code,),
            ).fetchone()
            if existing:
                self.send_json({
                    "reserved": True,
                    "alreadyReserved": True,
                    "slot": {
                        "id": existing["id"],
                        "startDate": existing["start_date"].isoformat(),
                        "endDate": (existing["start_date"] + timedelta(days=4)).isoformat(),
                        "taken": True,
                        "mine": True,
                    },
                })
                return

            chosen = connection.execute(
                "SELECT id, start_date, taken, access_code FROM sprint_slots WHERE id = %s FOR UPDATE",
                (slot_id,),
            ).fetchone()
            if not chosen:
                self.send_json({"message": "Cette période n’existe plus."}, HTTPStatus.NOT_FOUND)
                return
            if chosen["taken"]:
                self.send_json({"message": "Cette période vient d’être réservée. Choisis-en une autre."}, HTTPStatus.CONFLICT)
                return

            other_rows = connection.execute(
                "SELECT id, start_date FROM sprint_slots WHERE id <> %s",
                (slot_id,),
            ).fetchall()
            if any(ranges_overlap(start_date, row["start_date"]) for row in other_rows):
                self.send_json({"message": "Cette période chevauche déjà un autre sprint."}, HTTPStatus.CONFLICT)
                return

            row = connection.execute(
                """
                UPDATE sprint_slots
                SET start_date = %s, taken = TRUE, access_code = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING id, start_date, taken
                """,
                (start_date, code, slot_id),
            ).fetchone()

        self.send_json({
            "reserved": True,
            "slot": {
                "id": row["id"],
                "startDate": row["start_date"].isoformat(),
                "endDate": (row["start_date"] + timedelta(days=4)).isoformat(),
                "taken": True,
                "mine": True,
            },
        }, HTTPStatus.CREATED)

    def get_admin_planning(self):
        if not self.authenticated_admin():
            self.send_json({"message": "Session administrateur invalide ou expirée."}, HTTPStatus.UNAUTHORIZED)
            return
        with database_connection() as connection:
            rows = self.planning_rows(connection)
        slots = [self.serialize_planning_slot(row, include_identity=True) for row in rows]
        self.send_json({"slots": slots, "count": len(slots)})

    def create_admin_planning_slot(self):
        if not self.authenticated_admin():
            self.send_json({"message": "Session administrateur invalide ou expirée."}, HTTPStatus.UNAUTHORIZED)
            return
        body = self.read_body()
        start_date = parse_iso_date(body.get("startDate")) if isinstance(body, dict) else None
        if not start_date:
            self.send_json({"message": "Choisis une date de début valide."}, HTTPStatus.BAD_REQUEST)
            return

        with database_connection() as connection:
            connection.execute("LOCK TABLE sprint_slots IN SHARE ROW EXCLUSIVE MODE")
            rows = connection.execute("SELECT start_date FROM sprint_slots").fetchall()
            if any(ranges_overlap(start_date, row["start_date"]) for row in rows):
                self.send_json({"message": "Cette période chevauche déjà un sprint."}, HTTPStatus.CONFLICT)
                return
            row = connection.execute(
                """
                INSERT INTO sprint_slots (start_date, taken)
                VALUES (%s, FALSE)
                RETURNING id, start_date, taken
                """,
                (start_date,),
            ).fetchone()
        self.send_json({
            "created": True,
            "slot": {
                "id": row["id"], "startDate": row["start_date"].isoformat(),
                "endDate": (row["start_date"] + timedelta(days=4)).isoformat(), "taken": row["taken"],
                "reservedBy": None, "participantName": None,
            },
        }, HTTPStatus.CREATED)

    def update_admin_planning_slot(self):
        if not self.authenticated_admin():
            self.send_json({"message": "Session administrateur invalide ou expirée."}, HTTPStatus.UNAUTHORIZED)
            return
        body = self.read_body()
        slot_id = body.get("id") if isinstance(body, dict) else None
        if not isinstance(slot_id, int):
            self.send_json({"message": "Le créneau est invalide."}, HTTPStatus.BAD_REQUEST)
            return

        has_start_date = "startDate" in body
        start_date = parse_iso_date(body.get("startDate")) if has_start_date else None
        taken = body.get("taken") if "taken" in body else None
        if (has_start_date and not start_date) or (taken is not None and not isinstance(taken, bool)):
            self.send_json({"message": "La modification demandée est invalide."}, HTTPStatus.BAD_REQUEST)
            return

        with database_connection() as connection:
            connection.execute("LOCK TABLE sprint_slots IN SHARE ROW EXCLUSIVE MODE")
            current = connection.execute(
                "SELECT id, start_date, taken, access_code FROM sprint_slots WHERE id = %s FOR UPDATE",
                (slot_id,),
            ).fetchone()
            if not current:
                self.send_json({"message": "Ce créneau est introuvable."}, HTTPStatus.NOT_FOUND)
                return
            next_start = start_date or current["start_date"]
            rows = connection.execute("SELECT id, start_date FROM sprint_slots WHERE id <> %s", (slot_id,)).fetchall()
            if any(ranges_overlap(next_start, row["start_date"]) for row in rows):
                self.send_json({"message": "Cette période chevauche déjà un sprint."}, HTTPStatus.CONFLICT)
                return
            next_taken = current["taken"] if taken is None else taken
            next_code = current["access_code"] if next_taken else None
            connection.execute(
                """
                UPDATE sprint_slots
                SET start_date = %s, taken = %s, access_code = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (next_start, next_taken, next_code, slot_id),
            )
            row = next(item for item in self.planning_rows(connection) if item["id"] == slot_id)
        self.send_json({"updated": True, "slot": self.serialize_planning_slot(row, include_identity=True)})

    def delete_admin_planning_slot(self):
        if not self.authenticated_admin():
            self.send_json({"message": "Session administrateur invalide ou expirée."}, HTTPStatus.UNAUTHORIZED)
            return
        body = self.read_body()
        slot_id = body.get("id") if isinstance(body, dict) else None
        if not isinstance(slot_id, int):
            self.send_json({"message": "Le créneau est invalide."}, HTTPStatus.BAD_REQUEST)
            return
        with database_connection() as connection:
            row = connection.execute(
                "SELECT access_code FROM sprint_slots WHERE id = %s",
                (slot_id,),
            ).fetchone()
            if not row:
                self.send_json({"message": "Ce créneau est introuvable."}, HTTPStatus.NOT_FOUND)
                return
            if row["access_code"]:
                self.send_json({"message": "Libère d’abord la réservation avant de supprimer ce créneau."}, HTTPStatus.CONFLICT)
                return
            connection.execute("DELETE FROM sprint_slots WHERE id = %s", (slot_id,))
        self.send_json({"deleted": True, "id": slot_id})

    def get_draft(self):
        code = self.authenticated_code()
        if not code:
            self.send_json({"message": "Ta session a expiré."}, HTTPStatus.UNAUTHORIZED)
            return

        with database_connection() as connection:
            row = connection.execute(
                "SELECT answers FROM drafts WHERE access_code = %s",
                (code,),
            ).fetchone()
        self.send_json({"answers": row["answers"] if row else {}})

    def save_draft(self):
        code = self.authenticated_code()
        if not code:
            self.send_json(
                {"message": "Ta session a expiré. Saisis à nouveau ton code."},
                HTTPStatus.UNAUTHORIZED,
            )
            return

        body = self.read_body()
        answers = body.get("answers") if isinstance(body, dict) else None
        if not isinstance(answers, dict):
            self.send_json({"message": "Les réponses à sauvegarder sont invalides."}, HTTPStatus.BAD_REQUEST)
            return

        clean_answers = self.clean_answers(answers, require_complete=False)
        with database_connection() as connection:
            connection.execute(
                """
                INSERT INTO drafts (access_code, answers, saved_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (access_code)
                DO UPDATE SET answers = EXCLUDED.answers, saved_at = NOW()
                """,
                (code, Jsonb(clean_answers)),
            )
        self.send_json({"saved": True, "answerCount": len(clean_answers)})

    def save_submission(self):
        code = self.authenticated_code()
        if not code:
            self.send_json(
                {"message": "Ta session a expiré. Retourne à l’accueil et saisis à nouveau ton code."},
                HTTPStatus.UNAUTHORIZED,
            )
            return

        body = self.read_body()
        answers = body.get("answers") if isinstance(body, dict) else None
        if not isinstance(answers, dict):
            self.send_json({"message": "Les réponses envoyées sont invalides."}, HTTPStatus.BAD_REQUEST)
            return

        try:
            clean_answers = self.clean_answers(answers, require_complete=True)
        except ValueError as error:
            self.send_json({"message": str(error)}, HTTPStatus.BAD_REQUEST)
            return

        questions = get_questions()
        submission_id = secrets.token_hex(8)
        question_snapshot = [{"id": question["id"], "title": question["title"]} for question in questions]

        with database_connection() as connection:
            participant = connection.execute(
                "SELECT 1 FROM participants WHERE access_code = %s",
                (code,),
            ).fetchone()
            if not participant:
                self.send_json({"message": "Complète d’abord tes coordonnées."}, HTTPStatus.BAD_REQUEST)
                return
            connection.execute(
                """
                INSERT INTO submissions (id, access_code, questions, answers, submitted_at)
                VALUES (%s, %s, %s, %s, NOW())
                """,
                (submission_id, code, Jsonb(question_snapshot), Jsonb(clean_answers)),
            )
            connection.execute("DELETE FROM drafts WHERE access_code = %s", (code,))

        self.send_json({"saved": True, "submissionId": submission_id}, HTTPStatus.CREATED)

    def clean_answers(self, answers: dict, require_complete: bool) -> dict:
        questions = get_questions()
        if not questions:
            raise ConfigurationError("Aucune question valide n’est configurée.")

        clean_answers = {}
        for question in questions:
            value = answers.get(question["id"], "")
            if not isinstance(value, str):
                raise ValueError(f"La réponse « {question['title']} » est invalide.")
            value = value.strip()
            if require_complete and question["required"] and not value:
                raise ValueError(f"La réponse « {question['title']} » est incomplète.")
            if value or require_complete:
                clean_answers[question["id"]] = value
        return clean_answers

    def handle_server_error(self, error: Exception):
        if isinstance(error, ConfigurationError):
            logging.error("Configuration Vercel incomplète: %s", error)
            self.send_json({"message": "Le service est momentanément indisponible."}, HTTPStatus.SERVICE_UNAVAILABLE)
            return
        logging.exception("Erreur API onboarding")
        self.send_json({"message": "Une erreur interne est survenue."}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def send_json(self, payload, status=HTTPStatus.OK):
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)
