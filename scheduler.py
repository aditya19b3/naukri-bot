"""
scheduler.py
------------
Scheduler module for the Job Automation Hub.

Uses APScheduler to run daily automated jobs at a configurable time
(default: 09:00 AM IST). Supports:
  - Starting ALL enabled platforms at the scheduled time
  - Pause / resume functionality
  - Persistent state via scheduler_state.json
  - Configurable schedule time and platform list

Usage:
    from scheduler import init_scheduler, get_scheduler_status, ...
    init_scheduler(start_platform_callback)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
logger = logging.getLogger("scheduler")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s - %(name)s - %(message)s"))
    logger.addHandler(_handler)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STATE_FILE = Path("scheduler_state.json")
JOB_ID = "daily_auto_apply"
DEFAULT_TIMEZONE = "Asia/Kolkata"

DEFAULT_STATE: Dict[str, Any] = {
    "enabled": True,
    "paused": False,
    "schedule_time": "09:00",
    "timezone": DEFAULT_TIMEZONE,
    "enabled_platforms": ["naukri", "linkedin"],
    "last_run_time": None,
    "last_run_results": {},
}

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_scheduler: Optional[BackgroundScheduler] = None
_state: Dict[str, Any] = {}
_start_platform_cb: Optional[Callable[[str], Dict[str, Any]]] = None


# ========================================================================
# Persistence helpers
# ========================================================================

def _load_state() -> Dict[str, Any]:
    """Load scheduler state from disk, falling back to defaults."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                # Merge with defaults so new keys are always present
                merged = {**DEFAULT_STATE, **data}
                return merged
        except (json.JSONDecodeError, IOError) as exc:
            logger.warning("Failed to read %s, using defaults: %s", STATE_FILE, exc)
    return dict(DEFAULT_STATE)


def _save_state() -> None:
    """Persist current scheduler state to disk."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(_state, fh, indent=2, default=str)
    except IOError as exc:
        logger.error("Failed to write scheduler state: %s", exc)


# ========================================================================
# Scheduled job
# ========================================================================

def _scheduled_job() -> None:
    """
    The job that APScheduler fires at the configured time.

    Iterates through all enabled platforms and invokes the start callback
    for each one, collecting results.
    """
    global _state

    if _state.get("paused", False):
        logger.info("Scheduler is paused — skipping run.")
        return

    enabled_platforms: List[str] = _state.get("enabled_platforms", [])
    if not enabled_platforms:
        logger.info("No platforms enabled — nothing to start.")
        return

    logger.info("=== Scheduled run starting for platforms: %s ===", enabled_platforms)
    run_results: Dict[str, Any] = {}

    for platform_id in enabled_platforms:
        try:
            if _start_platform_cb is not None:
                result = _start_platform_cb(platform_id)
                run_results[platform_id] = result
                logger.info("Started %s: %s", platform_id, result)
            else:
                run_results[platform_id] = {"status": "error", "message": "No callback registered"}
                logger.error("No start callback registered for scheduler.")
        except Exception as exc:
            run_results[platform_id] = {"status": "error", "message": str(exc)}
            logger.error("Error starting %s: %s", platform_id, exc)

    # Persist run info
    _state["last_run_time"] = datetime.now().isoformat()
    _state["last_run_results"] = run_results
    _save_state()
    logger.info("=== Scheduled run completed. Results: %s ===", run_results)


# ========================================================================
# Internal helpers
# ========================================================================

def _build_cron_trigger() -> CronTrigger:
    """Build a CronTrigger from the current state's schedule_time and timezone."""
    schedule_time = _state.get("schedule_time", "09:00")
    timezone = _state.get("timezone", DEFAULT_TIMEZONE)

    try:
        hour, minute = map(int, schedule_time.split(":"))
    except (ValueError, AttributeError):
        logger.warning("Invalid schedule_time '%s', falling back to 09:00", schedule_time)
        hour, minute = 9, 0

    return CronTrigger(hour=hour, minute=minute, timezone=timezone)


def _reschedule_job() -> None:
    """Remove and re-add the daily job with the current trigger settings."""
    if _scheduler is None:
        return

    # Remove old job if it exists
    try:
        _scheduler.remove_job(JOB_ID)
    except Exception:
        pass  # Job may not exist yet

    if _state.get("enabled", True):
        trigger = _build_cron_trigger()
        _scheduler.add_job(
            _scheduled_job,
            trigger=trigger,
            id=JOB_ID,
            name="Daily Auto-Apply Job",
            replace_existing=True,
            misfire_grace_time=3600,  # 1 hour grace period
        )
        logger.info(
            "Job scheduled at %s (%s)",
            _state.get("schedule_time", "09:00"),
            _state.get("timezone", DEFAULT_TIMEZONE),
        )


# ========================================================================
# Public API
# ========================================================================

def init_scheduler(start_platform_callback: Callable[[str], Dict[str, Any]]) -> None:
    """
    Initialize the scheduler with a callback that starts a platform by name.

    Args:
        start_platform_callback: A function that accepts a platform_id string
            (e.g. "naukri", "linkedin") and starts the bot for that platform.
            It should return a dict with at least a "status" key.
    """
    global _scheduler, _state, _start_platform_cb

    _start_platform_cb = start_platform_callback
    _state = _load_state()

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.start()
    logger.info("APScheduler background scheduler started.")

    _reschedule_job()
    _save_state()
    logger.info("Scheduler initialized. State: %s", _state)


def get_scheduler_status() -> Dict[str, Any]:
    """
    Return the current scheduler status as a dict.

    Returns:
        dict with keys: enabled, paused, next_run_time, schedule_time,
        enabled_platforms, last_run_time, last_run_results, timezone
    """
    next_run: Optional[str] = None

    if _scheduler is not None:
        job = _scheduler.get_job(JOB_ID)
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

    return {
        "enabled": _state.get("enabled", True),
        "paused": _state.get("paused", False),
        "schedule_time": _state.get("schedule_time", "09:00"),
        "timezone": _state.get("timezone", DEFAULT_TIMEZONE),
        "enabled_platforms": _state.get("enabled_platforms", []),
        "next_run_time": next_run,
        "last_run_time": _state.get("last_run_time"),
        "last_run_results": _state.get("last_run_results", {}),
    }


def update_scheduler_config(
    schedule_time: Optional[str] = None,
    enabled_platforms: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Update the schedule time and/or the list of enabled platforms.

    Args:
        schedule_time: Time string in "HH:MM" 24-hour format (e.g. "09:00").
        enabled_platforms: List of platform IDs to run (e.g. ["naukri", "linkedin"]).

    Returns:
        Updated scheduler status dict.
    """
    global _state

    if schedule_time is not None:
        # Validate format
        try:
            h, m = map(int, schedule_time.split(":"))
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
            _state["schedule_time"] = schedule_time
        except (ValueError, AttributeError):
            logger.warning("Invalid schedule_time '%s' — ignoring.", schedule_time)

    if enabled_platforms is not None:
        _state["enabled_platforms"] = list(enabled_platforms)

    _save_state()
    _reschedule_job()

    return get_scheduler_status()


def pause_scheduler() -> Dict[str, Any]:
    """
    Pause the scheduler. The daily job remains scheduled but will skip execution.

    Returns:
        Updated scheduler status dict.
    """
    global _state
    _state["paused"] = True
    _save_state()
    logger.info("Scheduler paused.")
    return get_scheduler_status()


def resume_scheduler() -> Dict[str, Any]:
    """
    Resume the scheduler so the daily job executes again.

    Returns:
        Updated scheduler status dict.
    """
    global _state
    _state["paused"] = False
    _save_state()
    logger.info("Scheduler resumed.")
    return get_scheduler_status()


def shutdown_scheduler() -> None:
    """
    Cleanly shut down the APScheduler instance.
    Safe to call even if the scheduler was never initialized.
    """
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
            logger.info("Scheduler shut down cleanly.")
        except Exception as exc:
            logger.error("Error shutting down scheduler: %s", exc)
        finally:
            _scheduler = None
