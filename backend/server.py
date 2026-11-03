"""API local de CasaLab: proyectos/versiones SQLite, sesiones y validación."""
from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from . import camera_bridge
from .domain.geometry import validate_model
from .domain.requirements import interpret
from .storage.sqlite import connect, initialize

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
DATA_ROOT = PROJECT_ROOT / "data"
MAX_BODY = 2_000_000
SESSION_TTL = 60 * 60 * 24 * 7

def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def encode_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256$310000${salt.hex()}${digest.hex()}"


def check_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds, salt, expected = encoded.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False



class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_ROOT), **kwargs)

    def log_message(self, fmt, *args):
        # No registrar prompts, tokens, cookies ni contenido de proyectos.
        print(f"{self.client_address[0]} {args[0] if args else ''}")

    def read_body(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0 or size > MAX_BODY:
            raise ValueError("Tamaño de solicitud inválido")
        value = json.loads(self.rfile.read(size))
        if not isinstance(value, dict):
            raise ValueError("Se esperaba un objeto JSON")
        return value

    def send_json(self, data, status=200, extra_headers=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; media-src 'self' blob:; script-src 'self'; connect-src 'self'")
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def error(self, message, status=400):
        self.send_json({"error": message}, status)

    def current_user(self, db):
        cookie = self.headers.get("Cookie", "")
        token = next((part.split("=", 1)[1] for part in cookie.split(";") if part.strip().startswith("casalab_session=")), None)
        if not token:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        row = db.execute("SELECT users.id, users.email, users.role FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token_hash=? AND sessions.expires_at>?", (digest, int(time.time()))).fetchone()
        return dict(row) if row else None

    def require_user(self, db):
        user = self.current_user(db)
        if user is None:
            self.error("Inicia sesión para continuar", 401)
        return user

    def do_GET(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return super().do_GET()
        with connect() as db:
            if path == "/api/health":
                adb = shutil.which("adb")
                status = "no instalado" if not adb else "sin comprobar"
                detail = ""
                if adb:
                    try:
                        out = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=2, check=False)
                        devices = [line for line in out.stdout.splitlines()[1:] if line.strip() and not line.endswith("\tunauthorized")]
                        status = "conectado" if any(line.endswith("\tdevice") for line in devices) else "sin dispositivo autorizado"
                        detail = "; requiere aceptar la autorización de depuración USB en Android" if "unauthorized" in out.stdout else ""
                    except (OSError, subprocess.TimeoutExpired):
                        status = "ADB inaccesible en este entorno"
                return self.send_json({"adb": status, "detail": detail, "camera": camera_bridge.STATUS.get("message"), "camera_connected": camera_bridge.STATUS.get("connected", False), "tracking": camera_bridge.STATUS.get("tracking", False), "tracking_message": camera_bridge.STATUS.get("message"), "fps": camera_bridge.STATUS.get("fps", 0), "vision_dependency": camera_bridge.CV_ERROR, "bridge_error": getattr(self.server, "camera_bridge_error", None)})
            if path == "/api/ar/calibration":
                return self.send_json({"calibration": camera_bridge.CALIBRATION, "frame": [camera_bridge.CALIBRATION.get("image_width", 640), camera_bridge.CALIBRATION.get("image_height", 480)], "dictionary": "DICT_4X4_50", "marker_id": 0})
            if path == "/api/ar/marker.png":
                if camera_bridge.cv2 is None:
                    return self.error("Instala opencv-contrib-python para generar el marcador ArUco", 503)
                aruco = camera_bridge.cv2.aruco
                dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
                marker = aruco.generateImageMarker(dictionary, 0, 600) if hasattr(aruco, "generateImageMarker") else aruco.drawMarker(dictionary, 0, 600)
                ok, png = camera_bridge.cv2.imencode(".png", marker)
                if not ok:
                    return self.error("No se pudo generar el marcador", 500)
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(png)))
                self.send_header("Content-Disposition", "inline; filename=casalab-aruco-0.png")
                self.end_headers()
                return self.wfile.write(png.tobytes())
            if path == "/api/auth/me":
                return self.send_json({"user": self.current_user(db)})
            user = self.require_user(db)
            if user is None:
                return
            if path == "/api/users":
                if user["role"] != "admin":
                    return self.error("Se requiere el rol administrador", 403)
                rows = db.execute("SELECT id,email,role,created_at FROM users ORDER BY created_at").fetchall()
                return self.send_json({"users": [dict(r) for r in rows]})
            if path == "/api/projects":
                rows = db.execute("SELECT id,name,updated_at FROM projects WHERE owner_id=? ORDER BY updated_at DESC", (user["id"],)).fetchall()
                return self.send_json({"projects": [dict(r) for r in rows]})
            match = re.fullmatch(r"/api/projects/([\w-]+)(?:/(versions))?", path)
            if match:
                project_id, suffix = match.groups()
                project = db.execute("SELECT id,name,model_json,updated_at FROM projects WHERE id=? AND owner_id=?", (project_id, user["id"])).fetchone()
                if project is None:
                    return self.error("Proyecto no encontrado", 404)
                if suffix == "versions":
                    versions = db.execute("SELECT id,sequence,model_json,summary,created_at FROM versions WHERE project_id=? ORDER BY sequence DESC LIMIT 30", (project_id,)).fetchall()
                    values = [dict(r) for r in versions]
                    for row in values:
                        row["model"] = json.loads(row.pop("model_json"))
                    return self.send_json({"versions": values})
                value = dict(project)
                value["model"] = json.loads(value.pop("model_json"))
                return self.send_json(value)
            return self.error("Ruta no encontrada", 404)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self.read_body()
        except (ValueError, json.JSONDecodeError) as exc:
            return self.error(str(exc))
        if path in ("/api/auth/register", "/api/auth/login"):
            email = str(data.get("email", "")).strip().lower()
            password = data.get("password", "")
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(password) < 10:
                return self.error("Usa un correo válido y una contraseña de al menos 10 caracteres")
            with connect() as db:
                if path.endswith("register"):
                    if db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                        return self.error("Ese correo ya tiene una cuenta", 409)
                    first = db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
                    user_id = str(uuid.uuid4())
                    db.execute("INSERT INTO users VALUES(?,?,?,?,?)", (user_id, email, encode_password(password), "admin" if first else "client", now()))
                else:
                    row = db.execute("SELECT id,password_hash FROM users WHERE email=?", (email,)).fetchone()
                    if not row or not check_password(password, row["password_hash"]):
                        return self.error("Correo o contraseña incorrectos", 401)
                    user_id = row["id"]
                token = secrets.token_urlsafe(32)
                db.execute("INSERT INTO sessions VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user_id, int(time.time()) + SESSION_TTL))
                user = db.execute("SELECT id,email,role FROM users WHERE id=?", (user_id,)).fetchone()
            return self.send_json({"user": dict(user)}, 200, {"Set-Cookie": f"casalab_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_TTL}"})
        if path == "/api/auth/logout":
            with connect() as db:
                self.current_user(db)
                cookie = self.headers.get("Cookie", "")
                token = next((part.split("=", 1)[1] for part in cookie.split(";") if part.strip().startswith("casalab_session=")), None)
                if token:
                    db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
            return self.send_json({"ok": True}, extra_headers={"Set-Cookie": "casalab_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"})
        if path == "/api/interpret":
            text = data.get("text")
            if not isinstance(text, str) or not text.strip():
                return self.error("Describe la vivienda antes de generar")
            try:
                return self.send_json({"requirements": interpret(text[:8000])})
            except (ValueError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                return self.error(f"No se pudo interpretar la solicitud: {exc}", 502)
        if path == "/api/validate":
            issues = validate_model(data.get("model"))
            return self.send_json({"valid": not issues, "issues": issues})
        if path == "/api/ar/calibration":
            values = {k: data.get(k) for k in ("fx", "fy", "cx", "cy", "marker_size")}
            if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in values.values()):
                return self.error("Todos los parámetros de calibración deben ser numéricos")
            fx, fy, cx, cy, marker = (float(values[k]) for k in ("fx", "fy", "cx", "cy", "marker_size"))
            if not (1 <= fx <= 10000 and 1 <= fy <= 10000 and 0 <= cx <= 640 and 0 <= cy <= 480 and .01 <= marker <= .5):
                return self.error("Valores fuera de rango para cámara de 640 × 480 y marcador de 1 a 50 cm")
            distortion = data.get("distortion", camera_bridge.CALIBRATION.get("distortion", []))
            if not isinstance(distortion, list) or len(distortion) not in (0, 4, 5, 8, 12, 14) or any(not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > 10 for v in distortion):
                return self.error("La lista de distorsión debe tener 0, 4, 5, 8, 12 o 14 números finitos")
            camera_bridge.CALIBRATION.update({"fx": fx, "fy": fy, "cx": cx, "cy": cy, "marker_size": marker, "source": "calibración manual", "image_width": 640, "image_height": 480, "distortion": distortion})
            (DATA_ROOT / "calibration.json").write_text(json.dumps(camera_bridge.CALIBRATION, indent=2), encoding="utf-8")
            return self.send_json({"ok": True, "calibration": camera_bridge.CALIBRATION})
        role_match = re.fullmatch(r"/api/users/([\w-]+)/role", path)
        if role_match:
            with connect() as db:
                user = self.require_user(db)
                if not user:
                    return
                if user["role"] != "admin":
                    return self.error("Se requiere el rol administrador", 403)
                role = data.get("role")
                if role not in ("admin", "designer", "client"):
                    return self.error("Rol no reconocido")
                target_id = role_match.group(1)
                target = db.execute("SELECT role FROM users WHERE id=?", (target_id,)).fetchone()
                if not target:
                    return self.error("Usuario no encontrado", 404)
                if target_id == user["id"] and role != "admin":
                    admins = db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
                    if admins <= 1:
                        return self.error("No puedes quitar el último rol de administrador", 409)
                db.execute("UPDATE users SET role=? WHERE id=?", (role, target_id))
                return self.send_json({"ok": True, "id": target_id, "role": role})
        if path == "/api/projects":
            with connect() as db:
                user = self.require_user(db)
                if not user:
                    return
                model = data.get("model")
                issues = validate_model(model)
                if issues:
                    return self.send_json({"error": "El modelo no pasó validación", "issues": issues}, 422)
                project_id = str(data.get("id") or uuid.uuid4())
                name = str(data.get("name") or model.get("name") or "Proyecto")[:120]
                summary = str(data.get("summary") or "Guardado de diseño")[:240]
                serialized = json.dumps(model, ensure_ascii=False)
                prior = db.execute("SELECT id FROM projects WHERE id=? AND owner_id=?", (project_id, user["id"])).fetchone()
                if prior:
                    seq = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM versions WHERE project_id=?", (project_id,)).fetchone()[0]
                    db.execute("UPDATE projects SET name=?, model_json=?, updated_at=? WHERE id=?", (name, serialized, now(), project_id))
                else:
                    if data.get("id"):
                        return self.error("Proyecto no encontrado o no pertenece a este usuario", 404)
                    seq = 1
                    db.execute("INSERT INTO projects VALUES(?,?,?,?,?)", (project_id, user["id"], name, serialized, now()))
                version_id = str(uuid.uuid4())
                db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?)", (version_id, project_id, seq, serialized, summary, now()))
                return self.send_json({"ok": True, "id": project_id, "version": seq})
        return self.error("Ruta no encontrada", 404)

    def do_DELETE(self):
        match = re.fullmatch(r"/api/projects/([\w-]+)", urlparse(self.path).path)
        if not match:
            return self.error("Ruta no encontrada", 404)
        with connect() as db:
            user = self.require_user(db)
            if not user:
                return
            result = db.execute("DELETE FROM projects WHERE id=? AND owner_id=?", (match.group(1), user["id"]))
            if result.rowcount == 0:
                return self.error("Proyecto no encontrado", 404)
            return self.send_json({"ok": True})


def main():
    initialize()
    try:
        camera_bridge.start_camera_bridge()
        bridge_error = None
    except OSError as exc:
        bridge_error = f"No se pudo abrir el puerto local 8001: {exc}"
    print("CasaLab disponible en http://127.0.0.1:8000")
    http_server = ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8000"))), Handler)
    http_server.camera_bridge_error = bridge_error
    http_server.serve_forever()


if __name__ == "__main__":
    main()
