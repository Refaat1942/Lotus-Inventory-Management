import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import bcrypt

from config import DB_PATH, DEFAULT_ADMIN_PASS, DEFAULT_ADMIN_USER


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

PERMISSIONS = {
    "templates": "Download Templates",
    "engine_run": "Run Inventory Engine",
    "history": "Export Pullback History",
    "users_manage": "Manage Users & Permissions",
    "branding": "Manage Branding & Logo",
}

DEFAULT_BRANDING = {
    "app_title": "Lotus Inventory Management",
    "app_tagline": "Smart Inventory Engine",
    "accent_color": "#c0392b",
    "footer_text": "Copyright © Lotus Pharmacies 2026",
    "logo_filename": "",
}


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_permissions (
                user_id INTEGER NOT NULL,
                permission TEXT NOT NULL,
                PRIMARY KEY (user_id, permission),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS branding (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )

        admin = conn.execute(
            "SELECT id FROM users WHERE username = ?", (DEFAULT_ADMIN_USER,)
        ).fetchone()
        if not admin:
            conn.execute(
                "INSERT INTO users (username, password_hash, is_admin, is_active, created_at) VALUES (?, ?, 1, 1, ?)",
                (
                    DEFAULT_ADMIN_USER,
                    hash_password(DEFAULT_ADMIN_PASS),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

        for key, value in DEFAULT_BRANDING.items():
            conn.execute(
                "INSERT OR IGNORE INTO branding (key, value) VALUES (?, ?)",
                (key, value),
            )


def get_user_by_username(username: str):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def get_user_by_id(user_id: int):
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_permissions(user_id: int, is_admin: bool) -> list[str]:
    if is_admin:
        return list(PERMISSIONS.keys())
    with get_db() as conn:
        rows = conn.execute(
            "SELECT permission FROM user_permissions WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return [r["permission"] for r in rows]


def user_to_dict(row, include_permissions: bool = True) -> dict:
    data = {
        "id": row["id"],
        "username": row["username"],
        "is_admin": bool(row["is_admin"]),
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
    }
    if include_permissions:
        data["permissions"] = get_user_permissions(row["id"], bool(row["is_admin"]))
    return data


def list_users() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
    return [user_to_dict(r) for r in rows]


def create_user(username: str, password: str, is_admin: bool, permissions: list[str]) -> dict:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, is_admin, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
            (
                username,
                hash_password(password),
                int(is_admin),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        user_id = cur.lastrowid
        if not is_admin:
            for perm in permissions:
                if perm in PERMISSIONS:
                    conn.execute(
                        "INSERT INTO user_permissions (user_id, permission) VALUES (?, ?)",
                        (user_id, perm),
                    )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return user_to_dict(row)


def update_user(user_id: int, password: str | None, is_active: bool | None, is_admin: bool | None, permissions: list[str] | None) -> dict:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None
        if password:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(password), user_id),
            )
        if is_active is not None:
            conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (int(is_active), user_id))
        if is_admin is not None:
            conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (int(is_admin), user_id))
        if permissions is not None and not (is_admin if is_admin is not None else row["is_admin"]):
            conn.execute("DELETE FROM user_permissions WHERE user_id = ?", (user_id,))
            for perm in permissions:
                if perm in PERMISSIONS:
                    conn.execute(
                        "INSERT INTO user_permissions (user_id, permission) VALUES (?, ?)",
                        (user_id, perm),
                    )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return user_to_dict(row)


def delete_user(user_id: int, current_user_id: int) -> bool:
    if user_id == current_user_id:
        return False
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return True


def get_branding() -> dict:
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM branding").fetchall()
    branding = dict(DEFAULT_BRANDING)
    branding.update({r["key"]: r["value"] for r in rows})
    return branding


def update_branding(data: dict) -> dict:
    allowed = {"app_title", "app_tagline", "accent_color", "footer_text"}
    with get_db() as conn:
        for key, value in data.items():
            if key in allowed:
                conn.execute(
                    "INSERT INTO branding (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(value)),
                )
    return get_branding()


def set_logo_filename(filename: str):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO branding (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("logo_filename", filename),
        )
