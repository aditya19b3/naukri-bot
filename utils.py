"""
utils.py
--------
Shared utilities: WebDriver setup, logging configuration, retry decorator,
randomized human-like delays, and result output (CSV / JSON / Google Sheets).
"""

from __future__ import annotations

import csv
import functools
import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, TypeVar

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

T = TypeVar("T")


# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------
def setup_logger(name: str = "naukri_bot", log_dir: str = "logs") -> logging.Logger:
    """Configure a logger that writes to both console and a rotating file."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:
        # Avoid adding duplicate handlers if called more than once.
        return logger

    logger.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    file_handler = logging.FileHandler(Path(log_dir) / "bot.log", encoding="utf-8")
    file_handler.setFormatter(fmt)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


logger = setup_logger()


# ---------------------------------------------------------------------
# WebDriver setup
# ---------------------------------------------------------------------
def build_driver(headless: bool = False, chromedriver_path: str = "") -> webdriver.Chrome:
    """
    Create and return a configured Chrome WebDriver instance.

    If `chromedriver_path` is provided, it is used directly (useful on
    locked-down Windows machines). Otherwise webdriver-manager downloads
    and caches the correct driver automatically.
    """
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-notifications")
    options.add_argument("--log-level=3")
    # Reduce automation fingerprint (best-effort only; Naukri may still detect bots)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    if chromedriver_path:
        service = Service(executable_path=chromedriver_path)
    else:
        from webdriver_manager.chrome import ChromeDriverManager

        service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


# ---------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------
def retry(times: int = 3, delay: float = 2.0, exceptions: tuple = (Exception,)) -> Callable:
    """
    Retry a function call on transient failures (e.g. StaleElementReference,
    TimeoutException) with a short backoff between attempts.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exc = None
            for attempt in range(1, times + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:  # noqa: PERF203
                    last_exc = exc
                    logger.warning(
                        "Attempt %d/%d for %s failed: %s", attempt, times, func.__name__, exc
                    )
                    if attempt < times:
                        time.sleep(delay * attempt)  # simple linear backoff
            raise last_exc  # re-raise the final exception if all retries fail

        return wrapper

    return decorator


# ---------------------------------------------------------------------
# Human-like delay
# ---------------------------------------------------------------------
def human_delay(min_seconds: float = 2.0, max_seconds: float = 5.0) -> None:
    """Sleep for a randomized interval to avoid robotic, uniform timing."""
    time.sleep(random.uniform(min_seconds, max_seconds))


# ---------------------------------------------------------------------
# Result output
# ---------------------------------------------------------------------
def save_results_csv(results: List[Dict[str, Any]], path: Path) -> None:
    """Save results to CSV. Uses pandas if available, else falls back to csv module."""
    try:
        import pandas as pd

        df = pd.DataFrame(results, columns=["job_url", "status", "timestamp", "error_message"])
        df.to_csv(path, index=False)
    except ImportError:
        import csv

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["job_url", "status", "timestamp", "error_message"])
            writer.writeheader()
            writer.writerows(results)
    logger.info("Saved CSV results to %s", path)


def save_results_json(results: List[Dict[str, Any]], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info("Saved JSON results to %s", path)


def save_external_links(results: List[Dict[str, Any]], output_dir: Path) -> None:
    """
    Create a separate spreadsheet with external company links that require manual application.
    This helps track which jobs need to be applied to manually on company websites.
    """
    external_results = [r for r in results if r.get("external_link") or r.get("status") == "EXTERNAL_REDIRECT"]
    
    if not external_results:
        logger.info("No external redirects found; skipping external links spreadsheet.")
        return
    
    output_dir.mkdir(parents=True, exist_ok=True)
    external_csv_path = output_dir / "external_links.csv"
    
    with open(external_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["job_url", "company_website", "timestamp", "notes"])
        writer.writeheader()
        for result in external_results:
            writer.writerow({
                "job_url": result.get("job_url", ""),
                "company_website": result.get("external_link", ""),
                "timestamp": result.get("timestamp", ""),
                "notes": "Requires manual application on company website",
            })
    
    logger.info("Saved %d external links to %s", len(external_results), external_csv_path)



def upload_to_google_sheets(
    csv_path: Path,
    credentials_path: str,
    spreadsheet_id: str,
    worksheet_name: str = "Results",
) -> None:
    """
    Append the day's results to a Google Sheet.

    Requires a Google Cloud service account with Sheets API access, whose
    JSON key file is referenced by `credentials_path`. The target
    spreadsheet must be shared (Editor access) with the service account's
    email address ahead of time.

    This is intentionally isolated here so it can later be swapped out
    for a proper database/API call if this project becomes a SaaS backend.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        logger.error(
            "gspread/google-auth not installed. Run: pip install gspread google-auth"
        )
        return

    if not spreadsheet_id:
        logger.warning("GOOGLE_SHEETS_SPREADSHEET_ID not set; skipping Sheets upload.")
        return

    if not Path(credentials_path).exists():
        logger.error("Google service account file not found at %s; skipping Sheets upload.", credentials_path)
        return

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
    client = gspread.authorize(creds)

    sheet = client.open_by_key(spreadsheet_id)
    try:
        worksheet = sheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=worksheet_name, rows=1000, cols=10)
        worksheet.append_row(["job_url", "status", "timestamp", "error_message"])

    import csv

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [[r["job_url"], r["status"], r["timestamp"], r.get("error_message", "")] for r in reader]

    if rows:
        worksheet.append_rows(rows, value_input_option="USER_ENTERED")
        logger.info("Appended %d rows to Google Sheet '%s'.", len(rows), worksheet_name)
    else:
        logger.info("No rows to upload to Google Sheets.")
