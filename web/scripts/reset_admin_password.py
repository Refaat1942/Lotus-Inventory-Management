"""Reset default admin username/password from LOTUS_ADMIN_USER / LOTUS_ADMIN_PASS env vars.

Usage on VPS:
  cd /opt/lotus-inventory
  source venv/bin/activate
  python scripts/reset_admin_password.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DEFAULT_ADMIN_PASS, DEFAULT_ADMIN_USER
from database import ensure_default_admin, get_db, hash_password, normalize_username


def main():
    admin_user = normalize_username(DEFAULT_ADMIN_USER)
    with get_db() as conn:
        ensure_default_admin(conn)
        row = conn.execute(
            "SELECT id, username FROM users WHERE LOWER(TRIM(username)) = ? ORDER BY id LIMIT 1",
            (admin_user,),
        ).fetchone()
        if not row:
            print("ERROR: could not find or create admin user")
            sys.exit(1)
        conn.execute(
            "UPDATE users SET username = ?, password_hash = ?, is_active = 1, is_admin = 1 WHERE id = ?",
            (admin_user, hash_password(DEFAULT_ADMIN_PASS), row["id"]),
        )
    print(f"Admin login reset: username='{admin_user}' password from LOTUS_ADMIN_PASS env")


if __name__ == "__main__":
    main()
