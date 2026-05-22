from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "users.db"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                username       TEXT    UNIQUE NOT NULL,
                email          TEXT    DEFAULT '',
                password_hash  TEXT    NOT NULL,
                nombre         TEXT    DEFAULT '',
                plan           TEXT    DEFAULT 'beta',
                activo         INTEGER DEFAULT 1,
                es_admin       INTEGER DEFAULT 0,
                fecha_creacion TEXT    DEFAULT CURRENT_TIMESTAMP,
                ultimo_acceso  TEXT
            )
        """)
    _ensure_admin()


def _ensure_admin() -> None:
    from auth import hash_password
    admin_pass = os.getenv("ADMIN_PASSWORD", "admin123")
    with _conn() as c:
        existing = c.execute(
            "SELECT id FROM users WHERE username = 'admin'"
        ).fetchone()
        if not existing:
            c.execute(
                "INSERT INTO users (username,email,password_hash,nombre,es_admin) VALUES (?,?,?,?,?)",
                ("admin", "dmbruno61@gmail.com", hash_password(admin_pass), "Diego Bruno", 1),
            )


# ── Lectura ──────────────────────────────────────────────────────────────────

def get_user(username: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None


def list_users() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            """SELECT id, username, email, nombre, plan,
                      activo, es_admin, fecha_creacion, ultimo_acceso
               FROM users ORDER BY fecha_creacion DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


# ── Escritura ─────────────────────────────────────────────────────────────────

def create_user(
    username: str,
    password: str,
    nombre: str = "",
    email: str = "",
    plan: str = "beta",
) -> dict:
    from auth import hash_password
    with _conn() as c:
        c.execute(
            "INSERT INTO users (username,email,password_hash,nombre,plan) VALUES (?,?,?,?,?)",
            (username, email, hash_password(password), nombre, plan),
        )
        row = c.execute(
            "SELECT id,username,email,nombre,plan,activo,es_admin,fecha_creacion FROM users WHERE username=?",
            (username,),
        ).fetchone()
        return dict(row)


def toggle_user(username: str) -> bool:
    """Activa / desactiva un usuario. Devuelve el nuevo estado."""
    with _conn() as c:
        row = c.execute(
            "SELECT activo FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not row:
            return False
        new_state = 0 if row["activo"] else 1
        c.execute(
            "UPDATE users SET activo = ? WHERE username = ?", (new_state, username)
        )
        return bool(new_state)


def delete_user(username: str) -> None:
    with _conn() as c:
        c.execute(
            "DELETE FROM users WHERE username = ? AND es_admin = 0", (username,)
        )


def update_ultimo_acceso(username: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE users SET ultimo_acceso = ? WHERE username = ?",
            (datetime.utcnow().strftime("%Y-%m-%d %H:%M"), username),
        )
