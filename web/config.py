import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

HOST = os.getenv("LOTUS_HOST", "0.0.0.0")
PORT = int(os.getenv("LOTUS_PORT", "10000"))
SECRET_KEY = os.getenv("LOTUS_SECRET_KEY", "lotus-change-this-secret-in-production-2026")
SESSION_MAX_AGE = int(os.getenv("LOTUS_SESSION_HOURS", "24")) * 3600

DB_PATH = DATA_DIR / "lotus_app.db"
BRANDING_DIR = DATA_DIR / "branding"
BRANDING_DIR.mkdir(exist_ok=True)

DEFAULT_ADMIN_USER = os.getenv("LOTUS_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASS = os.getenv("LOTUS_ADMIN_PASS", "admin")
