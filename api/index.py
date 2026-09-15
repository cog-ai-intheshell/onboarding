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
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


BASE_DIR = Path(__file__).resolve().parents[1]
QUESTIONS_FILE = BASE_DIR / "questions.json"
ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")
MAX_BODY_SIZE = 2_000_000


class ConfigurationError(RuntimeError):
    """La configuration du service est absente ou invalide."""


def read_json(path: Path, fallback):
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def get_questions() -> list[dict]:
    data = read_json(QUESTIONS_FILE, {"questions": []})
    entries = data.get("questions", []) if isinstance(data, dict) else []
    questions = []
    seen_ids = set()

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        question_id = entry.get("id")
        title = entry.get("title")
        if not isinstance(question_id, str) or not ID_PATTERN.match(question_id) or question_id in seen_ids:
            continue
        if not isinstance(title, str) or not title.strip():
            continue
        seen_ids.add(question_id)
        questions.append({
            "id": question_id,
            "title": title.strip(),
            "helper": str(entry.get("helper", "")).strip(),
            "placeholder": str(entry.get("placeholder", "Ta réponse…")).strip(),
            "required": entry.get("required", True) is not False,
        })

    return questions


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
            elif route == "draft":
                self.get_draft()
            elif route == "admin-responses":
                self.get_admin_responses()
            else:
                self.send_json({"message": "Route introuvable."}, HTTPStatus.NOT_FOUND)
        except Exception as error:  # La réponse reste neutre, le détail part dans les logs Vercel.
            self.handle_server_error(error)

    def do_POST(self):
        try:
            route = self.requested_route()
            if route == "validate-code":
                self.validate_code()
            elif route == "admin-login":
                self.admin_login()
            elif route == "draft":
                self.save_draft()
            elif route == "submissions":
                self.save_submission()
            else:
                self.send_json({"message": "Route introuvable."}, HTTPStatus.NOT_FOUND)
        except Exception as error:  # La réponse reste neutre, le détail part dans les logs Vercel.
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
                SELECT id, submitted_at, access_code, questions, answers
                FROM submissions
                ORDER BY submitted_at DESC
                """
            ).fetchall()

        submissions = [{
            "id": row["id"],
            "submittedAt": row["submitted_at"].isoformat(),
            "accessCode": row["access_code"],
            "questions": row["questions"],
            "answers": row["answers"],
        } for row in rows]
        self.send_json({"submissions": submissions, "count": len(submissions)})

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
