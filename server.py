#!/usr/bin/env python3
"""Serveur autonome du site d'onboarding NXT, sans dépendance externe."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
CODES_FILE = BASE_DIR / "access_codes.json"
QUESTIONS_FILE = BASE_DIR / "questions.json"
RESPONSES_FILE = BASE_DIR / "responses.json"
DRAFTS_FILE = BASE_DIR / "drafts.json"
ADMIN_CONFIG_FILE = BASE_DIR / "admin_config.json"
SERVER_SECRET = os.environ.get("NXT_SERVER_SECRET", secrets.token_hex(32)).encode("utf-8")
WRITE_LOCK = threading.Lock()
ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")


def read_json(path: Path, fallback):
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def write_json_atomic(path: Path, data) -> None:
    temporary_file = path.with_suffix(".tmp")
    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    temporary_file.replace(path)


def get_codes() -> set[str]:
    """Relit le JSON à chaque appel : les nouveaux codes sont acceptés immédiatement."""
    data = read_json(CODES_FILE, {"codes": []})
    entries = data.get("codes", []) if isinstance(data, dict) else []
    codes = set()
    for entry in entries:
        code = entry.get("code", "") if isinstance(entry, dict) else entry
        if isinstance(code, str) and code.strip():
            codes.add(code.strip().upper())
    return codes


def get_questions() -> list[dict]:
    """Valide et renvoie les questions directement depuis questions.json."""
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
        min_length = bounded_int(entry.get("minLength"), 1, 1, 500)
        max_length = bounded_int(entry.get("maxLength"), 1200, 100, 5000)
        questions.append({
            "id": question_id,
            "title": title.strip(),
            "helper": str(entry.get("helper", "")).strip(),
            "placeholder": str(entry.get("placeholder", "Ta réponse…")).strip(),
            "required": entry.get("required", True) is not False,
            "minLength": min(min_length, max_length),
            "maxLength": max_length,
        })
    return questions


def create_access_token(code: str) -> str:
    expires_at = int(time.time()) + 4 * 60 * 60
    payload = f"{code}|{expires_at}"
    signature = hmac.new(SERVER_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}|{signature}"


def verify_access_token(token: str) -> str | None:
    try:
        code, expires_at, signature = token.split("|", 2)
        payload = f"{code}|{expires_at}"
        expected = hmac.new(SERVER_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected) or int(expires_at) < time.time():
            return None
        return code if code in get_codes() else None
    except (ValueError, TypeError):
        return None


def verify_admin_password(password: str) -> bool:
    environment_password = os.environ.get("NXT_ADMIN_PASSWORD")
    if environment_password is not None:
        return hmac.compare_digest(password, environment_password)

    config = read_json(ADMIN_CONFIG_FILE, {})
    try:
        salt = bytes.fromhex(config["passwordSalt"])
        expected_hash = bytes.fromhex(config["passwordHash"])
        iterations = int(config.get("iterations", 210_000))
        candidate_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(candidate_hash, expected_hash)
    except (KeyError, TypeError, ValueError):
        return False


def create_admin_token() -> str:
    expires_at = int(time.time()) + 2 * 60 * 60
    payload = f"admin|{expires_at}"
    signature = hmac.new(SERVER_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}|{signature}"


def verify_admin_token(token: str) -> bool:
    try:
        role, expires_at, signature = token.split("|", 2)
        payload = f"{role}|{expires_at}"
        expected = hmac.new(SERVER_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return role == "admin" and int(expires_at) >= time.time() and hmac.compare_digest(signature, expected)
    except (ValueError, TypeError):
        return False


class OnboardingHandler(SimpleHTTPRequestHandler):
    server_version = "NXTOnboarding/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        super().end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/questions":
            questions = get_questions()
            if not questions:
                self.send_json({"message": "Aucune question valide n’est configurée."}, HTTPStatus.SERVICE_UNAVAILABLE)
            else:
                self.send_json({"questions": questions})
            return
        if path == "/api/draft":
            self.get_draft()
            return
        if path == "/api/admin/responses":
            self.get_admin_responses()
            return
        if path in {"/access_codes.json", "/responses.json", "/drafts.json", "/admin_config.json", "/server.py"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/validate-code":
            self.validate_code()
        elif path == "/api/admin/login":
            self.admin_login()
        elif path == "/api/draft":
            self.save_draft()
        elif path == "/api/submissions":
            self.save_submission()
        else:
            self.send_json({"message": "Route introuvable."}, HTTPStatus.NOT_FOUND)

    def read_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 200_000:
                return None
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    def validate_code(self):
        body = self.read_body()
        code = body.get("code", "").strip().upper() if isinstance(body, dict) else ""
        if not code or code not in get_codes():
            self.send_json({"valid": False, "message": "Ce code n’est pas reconnu. Vérifie-le et réessaie."}, HTTPStatus.UNAUTHORIZED)
            return
        self.send_json({"valid": True, "accessToken": create_access_token(code)})

    def authenticated_code(self) -> str | None:
        authorization = self.headers.get("Authorization", "")
        return verify_access_token(authorization.removeprefix("Bearer ").strip())

    def authenticated_admin(self) -> bool:
        authorization = self.headers.get("Authorization", "")
        return verify_admin_token(authorization.removeprefix("Bearer ").strip())

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
        submissions = read_json(RESPONSES_FILE, [])
        if not isinstance(submissions, list):
            submissions = []
        submissions.sort(key=lambda item: item.get("submittedAt", ""), reverse=True)
        self.send_json({"submissions": submissions, "count": len(submissions)})

    def get_draft(self):
        code = self.authenticated_code()
        if not code:
            self.send_json({"message": "Ta session a expiré."}, HTTPStatus.UNAUTHORIZED)
            return
        drafts = read_json(DRAFTS_FILE, {})
        draft = drafts.get(code, {}) if isinstance(drafts, dict) else {}
        self.send_json({"answers": draft.get("answers", {}) if isinstance(draft, dict) else {}})

    def save_draft(self):
        code = self.authenticated_code()
        if not code:
            self.send_json({"message": "Ta session a expiré. Saisis à nouveau ton code."}, HTTPStatus.UNAUTHORIZED)
            return

        body = self.read_body()
        answers = body.get("answers") if isinstance(body, dict) else None
        if not isinstance(answers, dict):
            self.send_json({"message": "Les réponses à sauvegarder sont invalides."}, HTTPStatus.BAD_REQUEST)
            return

        questions = get_questions()
        clean_answers = {}
        for question in questions:
            value = answers.get(question["id"], "")
            if isinstance(value, str) and value.strip():
                clean_answers[question["id"]] = value.strip()[: question["maxLength"]]

        with WRITE_LOCK:
            drafts = read_json(DRAFTS_FILE, {})
            if not isinstance(drafts, dict):
                drafts = {}
            drafts[code] = {
                "savedAt": datetime.now(timezone.utc).isoformat(),
                "answers": clean_answers,
            }
            write_json_atomic(DRAFTS_FILE, drafts)

        self.send_json({"saved": True, "answerCount": len(clean_answers)})

    def save_submission(self):
        code = self.authenticated_code()
        if not code:
            self.send_json({"message": "Ta session a expiré. Retourne à l’accueil et saisis à nouveau ton code."}, HTTPStatus.UNAUTHORIZED)
            return

        body = self.read_body()
        answers = body.get("answers") if isinstance(body, dict) else None
        questions = get_questions()
        if not isinstance(answers, dict) or not questions:
            self.send_json({"message": "Les réponses envoyées sont invalides."}, HTTPStatus.BAD_REQUEST)
            return

        clean_answers = {}
        for question in questions:
            value = answers.get(question["id"], "")
            if not isinstance(value, str):
                self.send_json({"message": f"La réponse « {question['title']} » est invalide."}, HTTPStatus.BAD_REQUEST)
                return
            value = value.strip()
            if question["required"] and len(value) < question["minLength"]:
                self.send_json({"message": f"La réponse « {question['title']} » est incomplète."}, HTTPStatus.BAD_REQUEST)
                return
            clean_answers[question["id"]] = value[: question["maxLength"]]

        submission = {
            "id": secrets.token_hex(8),
            "submittedAt": datetime.now(timezone.utc).isoformat(),
            "accessCode": code,
            "questions": [{"id": question["id"], "title": question["title"]} for question in questions],
            "answers": clean_answers,
        }

        with WRITE_LOCK:
            submissions = read_json(RESPONSES_FILE, [])
            if not isinstance(submissions, list):
                submissions = []
            submissions.append(submission)
            write_json_atomic(RESPONSES_FILE, submissions)
            drafts = read_json(DRAFTS_FILE, {})
            if isinstance(drafts, dict) and code in drafts:
                del drafts[code]
                write_json_atomic(DRAFTS_FILE, drafts)

        self.send_json({"saved": True, "submissionId": submission["id"]}, HTTPStatus.CREATED)

    def send_json(self, payload, status=HTTPStatus.OK):
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)


def main():
    host = os.environ.get("NXT_HOST", "127.0.0.1")
    port = int(os.environ.get("NXT_PORT", "8000"))
    server = ThreadingHTTPServer((host, port), OnboardingHandler)
    print(f"NXT est prêt sur http://{host}:{port}")
    print("Arrête le serveur avec Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServeur arrêté.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
