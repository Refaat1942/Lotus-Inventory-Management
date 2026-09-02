import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import bcrypt

from config import BRANDING_DIR, DB_PATH, DEFAULT_ADMIN_PASS, DEFAULT_ADMIN_USER


def normalize_username(username: str) -> str:
    return username.strip().lower()


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

PERMISSIONS = {
    "purchase": "Access Purchase Module",
    "replenishment": "Access Replenishment Module",
    "templates": "Purchase — Download Templates",
    "engine_run": "Purchase — Run Engine",
    "history": "Purchase — Export History",
    "replenishment_templates": "Replenishment — Download Templates",
    "replenishment_run": "Replenishment — Run Engine",
    "replenishment_history": "Replenishment — Export History",
}

DEFAULT_BRANDING = {
    "app_title": "Lotus Inventory Management",
    "app_tagline": "Smart Inventory Engine",
    "accent_color": "#1e8449",
    "footer_text": "Copyright © Lotus Pharmacies 2026",
    "logo_filename": "",
}


def branding_with_logo() -> dict:
    branding = get_branding()
    path = resolve_logo_path(branding.get("logo_filename", ""))
    if path:
        branding["logo_filename"] = path.name
        branding["logo_url"] = f"/branding/{path.name}"
    else:
        branding["logo_url"] = None
    return branding


def resolve_logo_path(stored_filename: str = "") -> Path | None:
    """Find logo on disk; repair stale/missing DB filename after redeploys."""
    BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    name = (stored_filename or "").strip()
    if name:
        path = BRANDING_DIR / name
        if path.is_file():
            return path
    for pattern in ("logo.png", "logo.jpg", "logo.jpeg", "logo.webp", "logo.svg"):
        path = BRANDING_DIR / pattern
        if path.is_file():
            if name != path.name:
                set_logo_filename(path.name)
            return path
    for path in sorted(BRANDING_DIR.glob("logo.*")):
        if path.is_file():
            if name != path.name:
                set_logo_filename(path.name)
            return path
    return None


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

            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                ip_address TEXT,
                created_at TEXT NOT NULL
            );
            """
        )

        ensure_default_admin(conn)

        for row in conn.execute("SELECT id, username FROM users ORDER BY id").fetchall():
            low = normalize_username(row["username"])
            if low == row["username"]:
                continue
            conflict = conn.execute(
                "SELECT id FROM users WHERE LOWER(TRIM(username)) = ? AND id != ?",
                (low, row["id"]),
            ).fetchone()
            if not conflict:
                conn.execute(
                    "UPDATE users SET username = ? WHERE id = ?",
                    (low, row["id"]),
                )

        for key, value in DEFAULT_BRANDING.items():
            conn.execute(
                "INSERT OR IGNORE INTO branding (key, value) VALUES (?, ?)",
                (key, value),
            )

        # Grant module access to legacy users who had purchase features but no module flag
        purchase_legacy = {"templates", "engine_run", "history"}
        rows = conn.execute(
            "SELECT DISTINCT user_id, permission FROM user_permissions"
        ).fetchall()
        by_user: dict[int, set[str]] = {}
        for r in rows:
            by_user.setdefault(r["user_id"], set()).add(r["permission"])
        for user_id, perms in by_user.items():
            if perms & purchase_legacy and "purchase" not in perms:
                conn.execute(
                    "INSERT OR IGNORE INTO user_permissions (user_id, permission) VALUES (?, ?)",
                    (user_id, "purchase"),
                )
            if "replenishment" in perms:
                for sub in ("replenishment_templates", "replenishment_run", "replenishment_history"):
                    if sub not in perms:
                        conn.execute(
                            "INSERT OR IGNORE INTO user_permissions (user_id, permission) VALUES (?, ?)",
                            (user_id, sub),
                        )
            if "replenishment_run" in perms and "replenishment" not in perms:
                conn.execute(
                    "INSERT OR IGNORE INTO user_permissions (user_id, permission) VALUES (?, ?)",
                    (user_id, "replenishment"),
                )


def _find_user_by_username_ci(conn, username: str):
    norm = normalize_username(username)
    return conn.execute(
        "SELECT * FROM users WHERE LOWER(TRIM(username)) = ? ORDER BY id LIMIT 1",
        (norm,),
    ).fetchone()


def ensure_default_admin(conn):
    """Create or repair the default admin account (case-insensitive username)."""
    admin_user = normalize_username(DEFAULT_ADMIN_USER)
    row = _find_user_by_username_ci(conn, admin_user)
    if not row:
        conn.execute(
            "INSERT INTO users (username, password_hash, is_admin, is_active, created_at) VALUES (?, ?, 1, 1, ?)",
            (
                admin_user,
                hash_password(DEFAULT_ADMIN_PASS),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return

    if row["username"] != admin_user:
        dup = conn.execute(
            "SELECT id FROM users WHERE username = ? AND id != ?",
            (admin_user, row["id"]),
        ).fetchone()
        if not dup:
            conn.execute(
                "UPDATE users SET username = ? WHERE id = ?",
                (admin_user, row["id"]),
            )

    conn.execute(
        "UPDATE users SET is_active = 1, is_admin = 1 WHERE id = ?",
        (row["id"],),
    )

    if os.getenv("LOTUS_SYNC_ADMIN_PASSWORD", "").lower() in ("1", "true", "yes"):
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(DEFAULT_ADMIN_PASS), row["id"]),
        )


def get_user_by_username(username: str):
    norm = normalize_username(username)
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE LOWER(TRIM(username)) = ? ORDER BY id LIMIT 1",
            (norm,),
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
    username = normalize_username(username)
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE LOWER(TRIM(username)) = ?",
            (username,),
        ).fetchone()
        if existing:
            raise ValueError("Username already exists")
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


def update_user(
    user_id: int,
    username: str | None = None,
    password: str | None = None,
    is_active: bool | None = None,
    is_admin: bool | None = None,
    permissions: list[str] | None = None,
) -> dict:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None
        if username is not None:
            username = normalize_username(username)
            if len(username) < 3:
                raise ValueError("Username must be at least 3 characters")
            conflict = conn.execute(
                "SELECT id FROM users WHERE LOWER(TRIM(username)) = ? AND id != ?",
                (username, user_id),
            ).fetchone()
            if conflict:
                raise ValueError("Username already exists")
            conn.execute(
                "UPDATE users SET username = ? WHERE id = ?",
                (username, user_id),
            )
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
    return branding_with_logo()


def set_logo_filename(filename: str):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO branding (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("logo_filename", filename),
        )


def log_activity(user_id: int | None, username: str, action: str, details: str = "", ip_address: str = ""):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO activity_logs (user_id, username, action, details, ip_address, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, action, details, ip_address, datetime.now(timezone.utc).isoformat()),
        )


def get_activity_logs(limit: int = 300) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM activity_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_reports_summary() -> dict:
    from engine import DB_NAME
    import os

    with get_db() as conn:
        total_logins = conn.execute(
            "SELECT COUNT(*) AS c FROM activity_logs WHERE action = 'login'"
        ).fetchone()["c"]
        total_runs = conn.execute(
            "SELECT COUNT(*) AS c FROM activity_logs WHERE action = 'engine_run'"
        ).fetchone()["c"]
        total_users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        active_users = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE is_active = 1"
        ).fetchone()["c"]
        recent = conn.execute(
            "SELECT username, action, details, created_at FROM activity_logs ORDER BY id DESC LIMIT 10"
        ).fetchall()

    history_rows = 0
    history_runs = 0
    if os.path.exists(DB_NAME):
        try:
            hconn = sqlite3.connect(DB_NAME)
            history_rows = hconn.execute(
                "SELECT COUNT(*) FROM inventory_history"
            ).fetchone()[0]
            history_runs = hconn.execute(
                "SELECT COUNT(DISTINCT Run_Date) FROM inventory_history"
            ).fetchone()[0]
            hconn.close()
        except Exception:
            pass

    return {
        "total_logins": total_logins,
        "total_engine_runs": total_runs,
        "total_users": total_users,
        "active_users": active_users,
        "history_records": history_rows,
        "history_runs": history_runs,
        "recent_activity": [dict(r) for r in recent],
    }
