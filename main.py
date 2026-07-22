"""
main.py
-------
Entry point for the Naukri auto-apply bot.

Usage (Windows / macOS / Linux):
    python main.py

Configuration is read from a `.env` file (see .env.example) or real
environment variables -- see config.py for the full list of settings.
"""

from __future__ import annotations

import sys

from bot import NaukriBot
from config import load_config
from utils import build_driver, logger, save_results_csv, save_results_json, save_external_links, upload_to_google_sheets


def print_summary(summary: dict) -> None:
    print("\n" + "=" * 50)
    print("NAUKRI AUTO-APPLY BOT — RUN SUMMARY")
    print("=" * 50)
    print(f"  Applied:            {summary['applied']}")
    print(f"  Already applied:    {summary['already_applied']}")
    print(f"  External redirect:  {summary['external_redirect']}")
    print(f"  Skipped:            {summary['skipped']}")
    print(f"  Failed:             {summary['failed']}")
    print(f"  Total processed:    {summary['total']}")
    if summary.get("quota_hit"):
        print("  NOTE: Daily application quota was reached; run stopped early.")
    print("=" * 50 + "\n")


def main() -> int:
    try:
        config = load_config()
    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    logger.info(
        "Starting run | keywords=%s | location=%s | pages/keyword=%d | max_applications=%d | headless=%s",
        config.keywords,
        config.location,
        config.pages_per_keyword,
        config.max_applications,
        config.headless,
    )

    driver = build_driver(headless=config.headless, chromedriver_path=config.chromedriver_path)

    try:
        bot = NaukriBot(driver, config)
        results = bot.run()
    except SystemExit:
        # Raised deliberately (e.g. login failure) after logging a clear message.
        driver.quit()
        return 1
    except Exception as exc:  # noqa: BLE001 - top-level safety net
        logger.exception("Unexpected fatal error during run: %s", exc)
        driver.quit()
        return 1

    driver.quit()

    # Persist results regardless of how many jobs were processed.
    save_results_csv(results, config.csv_path)
    save_results_json(results, config.json_path)
    save_external_links(results, config.output_dir)

    if config.google_sheets_enabled:
        upload_to_google_sheets(
            csv_path=config.csv_path,
            credentials_path=config.google_sheets_credentials_path,
            spreadsheet_id=config.google_sheets_spreadsheet_id,
            worksheet_name=config.google_sheets_worksheet_name,
        )

    summary = bot.summary()
    print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
