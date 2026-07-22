"""
config.py
---------
Centralized configuration for the Naukri auto-apply bot.

Configuration is loaded from a .env file (via python-dotenv) with
environment variables taking precedence. This means the bot can be
configured either by:
  1. Creating a `.env` file (copy .env.example -> .env and fill it in), or
  2. Setting real OS environment variables (e.g. in CI/CD or a container).

No secrets are hardcoded anywhere in this file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Load variables from a local .env file if present. This is a no-op if the
# file doesn't exist, so it's safe to call unconditionally.
load_dotenv()


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    val = os.getenv(name)
    try:
        return int(val) if val is not None else default
    except ValueError:
        return default


def _get_list(name: str, default: List[str] | None = None) -> List[str]:
    val = os.getenv(name)
    if not val:
        return default or []
    return [item.strip() for item in val.split(",") if item.strip()]


@dataclass
class Config:
    # --- Credentials (never hardcode these; always sourced from env) ---
    email: str = field(default_factory=lambda: os.getenv("NAUKRI_EMAIL", ""))
    password: str = field(default_factory=lambda: os.getenv("NAUKRI_PASSWORD", ""))

    # --- Applicant profile ---
    first_name: str = field(default_factory=lambda: os.getenv("FIRST_NAME", ""))
    last_name: str = field(default_factory=lambda: os.getenv("LAST_NAME", ""))

    # --- Search parameters ---
    keywords: List[str] = field(default_factory=lambda: _get_list("KEYWORDS", ["python developer"]))
    location: str = field(default_factory=lambda: os.getenv("LOCATION", ""))
    pages_per_keyword: int = field(default_factory=lambda: _get_int("PAGES_PER_KEYWORD", 1))
    max_applications: int = field(default_factory=lambda: _get_int("MAX_APPLICATIONS", 10))

    # --- Browser ---
    headless: bool = field(default_factory=lambda: _get_bool("HEADLESS", False))
    chromedriver_path: str = field(default_factory=lambda: os.getenv("CHROMEDRIVER_PATH", ""))

    # --- Timing ---
    wait_timeout: int = field(default_factory=lambda: _get_int("WAIT_TIMEOUT", 15))
    min_delay: float = field(default_factory=lambda: float(os.getenv("MIN_DELAY", "2")))
    max_delay: float = field(default_factory=lambda: float(os.getenv("MAX_DELAY", "5")))

    # --- Output ---
    output_dir: str = field(default_factory=lambda: os.getenv("OUTPUT_DIR", "output"))
    csv_filename: str = field(default_factory=lambda: os.getenv("CSV_FILENAME", "results.csv"))
    json_filename: str = field(default_factory=lambda: os.getenv("JSON_FILENAME", "results.json"))

    # --- Google Sheets sync ---
    google_sheets_enabled: bool = field(default_factory=lambda: _get_bool("GOOGLE_SHEETS_ENABLED", False))
    google_sheets_credentials_path: str = field(
        default_factory=lambda: os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", "service_account.json")
    )
    google_sheets_spreadsheet_id: str = field(
        default_factory=lambda: os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
    )
    google_sheets_worksheet_name: str = field(
        default_factory=lambda: os.getenv("GOOGLE_SHEETS_WORKSHEET_NAME", "Results")
    )

    # --- Codex / OpenAI AI ---
    codex_api_key: str = field(default_factory=lambda: os.getenv("CODEX_API_KEY", ""))
    codex_api_base_url: str = field(default_factory=lambda: os.getenv("CODEX_API_BASE_URL", "https://api.openai.com/v1/chat/completions"))
    codex_model: str = field(default_factory=lambda: os.getenv("CODEX_MODEL", "gpt-4o-mini"))

    # --- Applicant Profile Details for chatbot answering ---
    years_of_experience: str = field(default_factory=lambda: os.getenv("YEARS_OF_EXPERIENCE", "3"))
    current_ctc: str = field(default_factory=lambda: os.getenv("CURRENT_CTC", ""))
    expected_ctc: str = field(default_factory=lambda: os.getenv("EXPECTED_CTC", ""))
    notice_period: str = field(default_factory=lambda: os.getenv("NOTICE_PERIOD", ""))
    skills: str = field(default_factory=lambda: os.getenv("SKILLS", ""))
    current_location: str = field(default_factory=lambda: os.getenv("CURRENT_LOCATION", ""))
    preferred_locations: str = field(default_factory=lambda: os.getenv("PREFERRED_LOCATIONS", ""))

    # --- Extended applicant profile details ---
    gender: str = field(default_factory=lambda: os.getenv("GENDER", "Male"))
    graduation_year: str = field(default_factory=lambda: os.getenv("GRADUATION_YEAR", "2024"))
    highest_qualification: str = field(default_factory=lambda: os.getenv("HIGHEST_QUALIFICATION", "B.Tech"))
    current_company: str = field(default_factory=lambda: os.getenv("CURRENT_COMPANY", ""))
    work_authorization: str = field(default_factory=lambda: os.getenv("WORK_AUTHORIZATION", "Yes"))
    shift_flexibility: str = field(default_factory=lambda: os.getenv("SHIFT_FLEXIBILITY", "Yes"))


    def validate(self) -> None:
        """Raise a clear error early if required settings are missing."""
        missing = []
        if not self.email:
            missing.append("NAUKRI_EMAIL")
        if not self.password:
            missing.append("NAUKRI_PASSWORD")
        if not self.keywords:
            missing.append("KEYWORDS")
        if missing:
            raise ValueError(
                f"Missing required configuration values: {', '.join(missing)}. "
                "Set them in your .env file or as environment variables."
            )

    @property
    def csv_path(self) -> Path:
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        return Path(self.output_dir) / self.csv_filename

    @property
    def json_path(self) -> Path:
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        return Path(self.output_dir) / self.json_filename


def load_config() -> Config:
    """Load and validate configuration. Call this once at startup."""
    cfg = Config()
    cfg.validate()
    return cfg
