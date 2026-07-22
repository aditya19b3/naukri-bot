import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict

DB_PATH = Path("output/naukri_users.db")
EXAMPLE_ENV_PATH = Path(".env.example")
logger = logging.getLogger("db")

def init_db():
    """Initialize the SQLite database and create the user_profiles table if it doesn't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            email TEXT PRIMARY KEY,
            settings_json TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    logger.info("SQLite Database initialized: %s", DB_PATH.resolve())

def _load_defaults_from_example() -> Dict[str, str]:
    """Parse .env.example to get baseline keys and values as defaults for new users."""
    defaults: Dict[str, str] = {}
    if EXAMPLE_ENV_PATH.exists():
        try:
            with open(EXAMPLE_ENV_PATH, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    defaults[key.strip()] = val.strip()
        except Exception as exc:
            logger.warning("Failed to parse .env.example: %s", exc)
    return defaults

def get_user_settings(email: str) -> Dict[str, str]:
    """Retrieve settings dictionary for a specific user. Falls back to defaults if not found."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT settings_json FROM user_profiles WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()

    if row:
        try:
            return json.loads(row[0])
        except Exception as exc:
            logger.error("Failed to parse settings JSON for user %s: %s", email, exc)

    # Return defaults for new user
    return _load_defaults_from_example()

def save_user_settings(email: str, settings: Dict[str, str]) -> None:
    """Save user settings dict to SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    settings_json = json.dumps(settings, ensure_ascii=False)
    cursor.execute("""
        INSERT INTO user_profiles (email, settings_json, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(email) DO UPDATE SET
            settings_json = excluded.settings_json,
            updated_at = CURRENT_TIMESTAMP
    """, (email, settings_json))
    conn.commit()
    conn.close()
    logger.info("Saved settings for user: %s", email)
