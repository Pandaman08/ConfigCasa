"""Persistencia SQLite y carga de configuración almacenada."""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import json
import os
import sqlite3
from .. import camera_bridge

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data"
DB_PATH = Path(os.environ.get("CASALAB_DB", DATA_ROOT / "casalab.sqlite3"))


@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','designer','client')), created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL,
            model_json TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS versions (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            sequence INTEGER NOT NULL, model_json TEXT NOT NULL, summary TEXT NOT NULL,
            created_at TEXT NOT NULL, UNIQUE(project_id, sequence)
        );
        CREATE INDEX IF NOT EXISTS versions_project ON versions(project_id, sequence DESC);
        """)
        columns = {row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()}
        if "name" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN name TEXT NOT NULL DEFAULT ''")
    calibration_file = DATA_ROOT / "calibration.json"
    if calibration_file.exists():
        try:
            saved = json.loads(calibration_file.read_text(encoding="utf-8"))
            for key in ("fx", "fy", "cx", "cy", "marker_size", "image_width", "image_height"):
                if isinstance(saved.get(key), (int, float)):
                    camera_bridge.CALIBRATION[key] = float(saved[key])
            if isinstance(saved.get("distortion"), list):
                camera_bridge.CALIBRATION["distortion"] = saved["distortion"]
            camera_bridge.CALIBRATION["source"] = "calibración manual"
        except (OSError, json.JSONDecodeError):
            pass
