"""
backend.py
----------
Unified FastAPI backend server for the Job Automation Hub.

Supports multiple job-application platforms (Naukri, LinkedIn, etc.) with:
  - Per-platform config, start/stop, logs, and results endpoints
  - An APScheduler-based daily scheduler for automated runs
  - Full backward compatibility with the original Naukri-only API

Usage:
    python backend.py
"""

from __future__ import annotations

import ast
import csv
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from scheduler import (
    init_scheduler,
    get_scheduler_status,
    update_scheduler_config,
    pause_scheduler,
    resume_scheduler,
    shutdown_scheduler,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("backend")

# ---------------------------------------------------------------------------
# Platform Registry
# ---------------------------------------------------------------------------
PLATFORMS: Dict[str, Dict[str, Any]] = {
    "naukri": {
        "name": "Naukri.com",
        "script": "main.py",
        "cwd": ".",                              # root project directory
        "log_path": "output/bot.log",
        "results_path": "output/results.json",
        "config_type": "env",                    # reads from .env
        "color": "#6366f1",
        "icon": "briefcase",
    },
    "linkedin": {
        "name": "LinkedIn",
        "script": "main_linkedin.py",
        "cwd": "linkedin",                       # run from linkedin/ sub-dir
        "log_path": "linkedin/logs/log.txt",
        "results_path": "linkedin/all excels/all_applied_applications_history.csv",
        "config_type": "python",                 # reads from python config files
        "color": "#0A66C2",
        "icon": "linkedin",
    },
}

# LinkedIn Python config files (order matters for display grouping)
LINKEDIN_CONFIG_FILES: List[str] = [
    "personals.py",
    "questions.py",
    "resume.py",
    "search.py",
    "secrets.py",
    "settings.py",
]

# ---------------------------------------------------------------------------
# Process Tracking
# ---------------------------------------------------------------------------
# Maps platform_id -> {"process": Popen, "start_time": float, "log_file": IO}
platform_processes: Dict[str, Dict[str, Any]] = {}

# Legacy aliases — kept so old endpoints work without any special-casing
ENV_PATH = Path(".env")
LOG_PATH = Path("output/bot.log")
RESULTS_PATH = Path("output/results.json")

# Ensure output directory exists
Path("output").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class ConfigModel(BaseModel):
    """Model for Naukri .env config updates."""
    settings: Dict[str, str]


class LinkedInConfigModel(BaseModel):
    """Model for LinkedIn Python config updates."""
    settings: Dict[str, Any]


class SchedulerConfigModel(BaseModel):
    """Model for scheduler config updates."""
    schedule_time: Optional[str] = None
    enabled_platforms: Optional[List[str]] = None


# ========================================================================
# Lifespan: initialize and shut down scheduler with the app
# ========================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler — startup & shutdown logic."""
    # ---- STARTUP ----
    logger.info("Initializing scheduler…")
    init_scheduler(start_platform_bot)
    logger.info("Scheduler ready.")

    yield  # Application is running

    # ---- SHUTDOWN ----
    logger.info("Shutting down scheduler…")
    shutdown_scheduler()

    # Kill any running bot subprocesses
    for pid, info in list(platform_processes.items()):
        proc: subprocess.Popen = info.get("process")
        if proc and proc.poll() is None:
            try:
                proc.kill()
                logger.info("Killed lingering process for %s (PID %s)", pid, proc.pid)
            except Exception:
                pass
    logger.info("Backend shut down cleanly.")


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Job Automation Hub API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========================================================================
# Utility helpers — .env reading/writing (Naukri)
# ========================================================================

def load_env_dict() -> Dict[str, str]:
    """Load all variables from .env as a simple key-value dictionary."""
    env_dict: Dict[str, str] = {}
    if not ENV_PATH.exists():
        example_path = Path(".env.example")
        if example_path.exists():
            return _load_env_from_file(example_path)
        return env_dict
    return _load_env_from_file(ENV_PATH)


def _load_env_from_file(path: Path) -> Dict[str, str]:
    """Parse a dotenv-style file and return key-value pairs."""
    env_dict: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            env_dict[key.strip()] = val.strip()
    return env_dict


def save_env_dict(new_settings: Dict[str, str]) -> None:
    """Update .env keys while preserving comments, order, and existing values."""
    lines: List[str] = []
    updated_keys: set = set()

    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, _ = stripped.split("=", 1)
                    key = key.strip()
                    if key in new_settings:
                        lines.append(f"{key}={new_settings[key]}\n")
                        updated_keys.add(key)
                        continue
                lines.append(line)

    # Append brand-new keys
    for key, val in new_settings.items():
        if key not in updated_keys:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(f"{key}={val}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as fh:
        fh.writelines(lines)


# ========================================================================
# Utility helpers — LinkedIn Python config reading/writing
# ========================================================================

def _parse_python_value(raw: str) -> Any:
    """
    Safely parse a Python literal value from a string.

    Supports strings, numbers, booleans, and lists of strings.
    Falls back to returning the raw string if parsing fails.
    """
    raw = raw.strip()

    # Try ast.literal_eval for safe parsing of Python literals
    try:
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return raw


def _read_linkedin_config_file(filepath: Path) -> Dict[str, Any]:
    """
    Parse a single LinkedIn Python config file and return variables as a dict.

    Matches lines of the form:
        variable_name = <value>
    where <value> can be a string, number, boolean, or list.
    """
    config: Dict[str, Any] = {}

    if not filepath.exists():
        return config

    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                # Skip blank lines, comments, imports, function defs, etc.
                if (
                    not line
                    or line.startswith("#")
                    or line.startswith("import ")
                    or line.startswith("from ")
                    or line.startswith("def ")
                    or line.startswith("class ")
                ):
                    continue

                # Match: variable_name = value
                match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", line)
                if match:
                    var_name = match.group(1)
                    raw_value = match.group(2)
                    config[var_name] = _parse_python_value(raw_value)
    except IOError as exc:
        logger.warning("Could not read LinkedIn config %s: %s", filepath, exc)

    return config


def read_all_linkedin_configs() -> Dict[str, Any]:
    """
    Read ALL LinkedIn Python config files and return a merged dict.

    Keys are prefixed with the filename (without .py) to avoid collisions,
    e.g. personals.first_name, search.search_terms.

    Also returns a flat view under each filename group for the frontend.
    """
    linkedin_dir = Path("linkedin")
    merged: Dict[str, Any] = {}

    for config_file in LINKEDIN_CONFIG_FILES:
        filepath = linkedin_dir / config_file
        file_key = config_file.replace(".py", "")
        file_config = _read_linkedin_config_file(filepath)
        merged[file_key] = file_config

    return merged


def _python_value_to_str(value: Any) -> str:
    """Convert a Python value back to its source-code representation."""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, str):
        # Use double quotes, escaping any inner double quotes
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        items = ", ".join(_python_value_to_str(item) for item in value)
        return f"[{items}]"
    # Fallback
    return repr(value)


def _write_linkedin_config_var(filepath: Path, var_name: str, new_value: Any) -> bool:
    """
    Update a single variable assignment in a LinkedIn Python config file.

    Finds the line matching `var_name = ...` and replaces the value portion.

    Returns True if the variable was found and updated, False otherwise.
    """
    if not filepath.exists():
        return False

    new_value_str = _python_value_to_str(new_value)
    pattern = re.compile(rf"^({re.escape(var_name)}\s*=\s*)(.+)$")
    updated = False
    lines: List[str] = []

    with open(filepath, "r", encoding="utf-8") as fh:
        for line in fh:
            match = pattern.match(line.rstrip("\n"))
            if match and not updated:
                lines.append(f"{match.group(1)}{new_value_str}\n")
                updated = True
            else:
                lines.append(line)

    if updated:
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.writelines(lines)

    return updated


def write_linkedin_configs(settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    Write LinkedIn config settings.

    Accepts a dict keyed by config-file group (e.g. "personals", "search")
    with nested dicts of variable -> value.

    Example input:
        {
            "personals": {"first_name": "Aditya", "years_of_experience": "3"},
            "search": {"search_terms": ["Java Developer", "React Developer"]}
        }

    Returns a summary dict with counts of updated variables.
    """
    linkedin_dir = Path("linkedin")
    summary: Dict[str, Any] = {"updated": 0, "not_found": 0, "errors": []}

    for file_key, variables in settings.items():
        if not isinstance(variables, dict):
            continue

        # Map the group key back to the filename
        config_filename = f"{file_key}.py"
        if config_filename not in LINKEDIN_CONFIG_FILES:
            summary["errors"].append(f"Unknown config group: {file_key}")
            continue

        filepath = linkedin_dir / config_filename

        for var_name, new_value in variables.items():
            try:
                if _write_linkedin_config_var(filepath, var_name, new_value):
                    summary["updated"] += 1
                else:
                    summary["not_found"] += 1
            except Exception as exc:
                summary["errors"].append(f"{file_key}.{var_name}: {exc}")

    return summary


# ========================================================================
# Utility helpers — LinkedIn results (CSV)
# ========================================================================

def _parse_linkedin_results_csv() -> List[Dict[str, str]]:
    """
    Parse the LinkedIn application-history CSV and return as a list of dicts.

    Expected columns: Job_ID, Date_Applied, Title, Company, HR_Name,
    HR_Link, Job_Link, External_Job_link
    """
    csv_path = Path(PLATFORMS["linkedin"]["results_path"])
    results: List[Dict[str, str]] = []

    if not csv_path.exists():
        return results

    try:
        with open(csv_path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                results.append(dict(row))
    except Exception as exc:
        logger.warning("Failed to parse LinkedIn CSV: %s", exc)

    return results


# ========================================================================
# Generic platform bot start/stop
# ========================================================================

def _find_python_exe() -> str:
    """Find the best Python executable, preferring a local venv."""
    python_exe = sys.executable
    for venv_dir in [".venv", "venv"]:
        possible = Path(venv_dir) / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        if possible.exists():
            python_exe = str(possible.resolve())
            break
    return python_exe


def start_platform_bot(platform_id: str) -> Dict[str, Any]:
    """
    Start a platform's bot subprocess.

    This function is used BOTH by the HTTP endpoints and by the scheduler
    callback, ensuring a single code-path for launching bots.

    Args:
        platform_id: Key from the PLATFORMS registry (e.g. "naukri", "linkedin").

    Returns:
        A dict with "status" and optional "pid" / "message".
    """
    if platform_id not in PLATFORMS:
        return {"status": "error", "message": f"Unknown platform: {platform_id}"}

    platform = PLATFORMS[platform_id]

    # Check if already running
    if platform_id in platform_processes:
        proc_info = platform_processes[platform_id]
        proc: subprocess.Popen = proc_info["process"]
        if proc.poll() is None:
            return {"status": "already_running", "message": f"{platform['name']} bot is already running."}
        else:
            # Clean up finished process
            _cleanup_process(platform_id)

    log_path = Path(platform["log_path"])
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Clear previous logs for a clean run
    try:
        if log_path.exists():
            log_path.unlink()
    except Exception:
        pass

    try:
        log_file = open(log_path, "w", encoding="utf-8")
        python_exe = _find_python_exe()
        cmd = [python_exe, platform["script"]]

        # Resolve the working directory relative to the project root
        cwd = Path(platform["cwd"]).resolve() if platform["cwd"] != "." else Path(".").resolve()

        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=str(cwd),
            creationflags=creation_flags,
        )

        platform_processes[platform_id] = {
            "process": proc,
            "start_time": time.time(),
            "log_file": log_file,
        }

        logger.info("Started %s bot (PID %s)", platform["name"], proc.pid)
        return {
            "status": "started",
            "message": f"{platform['name']} bot started successfully.",
            "pid": proc.pid,
        }

    except Exception as exc:
        logger.error("Failed to start %s bot: %s", platform["name"], exc)
        return {"status": "error", "message": f"Failed to start {platform['name']} bot: {exc}"}


def stop_platform_bot(platform_id: str) -> Dict[str, Any]:
    """
    Stop a platform's bot subprocess.

    Args:
        platform_id: Key from the PLATFORMS registry.

    Returns:
        A dict with "status" and "message".
    """
    if platform_id not in PLATFORMS:
        return {"status": "error", "message": f"Unknown platform: {platform_id}"}

    platform = PLATFORMS[platform_id]

    if platform_id not in platform_processes:
        return {"status": "not_running", "message": f"{platform['name']} bot is not running."}

    proc_info = platform_processes[platform_id]
    proc: subprocess.Popen = proc_info["process"]

    if proc.poll() is not None:
        _cleanup_process(platform_id)
        return {"status": "not_running", "message": f"{platform['name']} bot is not running."}

    try:
        # Graceful stop
        if sys.platform == "win32":
            os.kill(proc.pid, signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()

        # Wait up to 3 seconds for clean exit
        for _ in range(10):
            if proc.poll() is not None:
                break
            time.sleep(0.3)

        # Force kill if still alive
        if proc.poll() is None:
            proc.kill()

        _cleanup_process(platform_id)
        return {"status": "stopped", "message": f"{platform['name']} bot stopped successfully."}

    except Exception as exc:
        # Last-resort force kill
        try:
            proc.kill()
            _cleanup_process(platform_id)
            return {"status": "force_stopped", "message": f"{platform['name']} bot force killed. Error: {exc}"}
        except Exception as err:
            return {"status": "error", "message": f"Failed to terminate {platform['name']} bot: {err}"}


def _cleanup_process(platform_id: str) -> None:
    """Clean up tracking state for a finished / killed process."""
    if platform_id in platform_processes:
        info = platform_processes.pop(platform_id)
        log_file = info.get("log_file")
        if log_file and not log_file.closed:
            try:
                log_file.close()
            except Exception:
                pass


def _get_platform_running_status(platform_id: str) -> Dict[str, Any]:
    """Return running/elapsed/pid info for a platform subprocess."""
    is_running = False
    pid = None
    elapsed = 0.0

    if platform_id in platform_processes:
        info = platform_processes[platform_id]
        proc: subprocess.Popen = info["process"]
        if proc.poll() is None:
            is_running = True
            pid = proc.pid
            start_t = info.get("start_time")
            if start_t:
                elapsed = time.time() - start_t
        else:
            _cleanup_process(platform_id)

    return {"running": is_running, "pid": pid, "elapsed_seconds": int(elapsed)}


# ========================================================================
#  API — Platforms overview
# ========================================================================

@app.get("/api/platforms")
def get_platforms():
    """
    Return the platform registry enriched with live running status.

    Each platform dict gains a "running" boolean and "pid" / "elapsed_seconds".
    """
    result: Dict[str, Any] = {}
    for pid, pinfo in PLATFORMS.items():
        entry = dict(pinfo)
        entry.update(_get_platform_running_status(pid))
        result[pid] = entry
    return result


# ========================================================================
#  API — Naukri endpoints (UNCHANGED behaviour)
# ========================================================================

@app.get("/api/config")
def get_config():
    """Retrieve all current Naukri bot configuration parameters from .env."""
    try:
        return load_env_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read environment configuration: {exc}")


@app.post("/api/config")
def update_config(data: ConfigModel):
    """Update Naukri bot configuration parameters in .env."""
    try:
        save_env_dict(data.settings)
        return {"status": "success", "message": "Configuration saved successfully."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save environment configuration: {exc}")


@app.get("/api/status")
def get_status():
    """Get the current running status and metrics of the Naukri bot."""
    status = _get_platform_running_status("naukri")

    # Calculate stats from results file
    stats: Dict[str, Any] = {
        "applied": 0,
        "already_applied": 0,
        "external_redirect": 0,
        "skipped": 0,
        "failed": 0,
        "total": 0,
        "quota_hit": False,
    }

    if RESULTS_PATH.exists():
        try:
            with open(RESULTS_PATH, "r", encoding="utf-8") as fh:
                results = json.load(fh)
                if isinstance(results, list):
                    stats["total"] = len(results)
                    for r in results:
                        s = r.get("status", "").upper()
                        if s == "APPLIED":
                            stats["applied"] += 1
                        elif s == "ALREADY_APPLIED":
                            stats["already_applied"] += 1
                        elif s == "EXTERNAL_REDIRECT":
                            stats["external_redirect"] += 1
                        elif s == "SKIPPED":
                            stats["skipped"] += 1
                        elif s == "FAILED":
                            stats["failed"] += 1
        except Exception:
            pass

    # Check for quota in logs
    if LOG_PATH.exists():
        try:
            with open(LOG_PATH, "r", encoding="utf-8") as fh:
                log_content = fh.read()
                if "quota" in log_content.lower() or "limit has been reached" in log_content.lower():
                    stats["quota_hit"] = True
        except Exception:
            pass

    return {
        "running": status["running"],
        "pid": status["pid"],
        "elapsed_seconds": status["elapsed_seconds"],
        "stats": stats,
    }


@app.post("/api/start")
def start_bot():
    """Start the Naukri bot subprocess (backward-compatible endpoint)."""
    result = start_platform_bot("naukri")

    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])

    return result


@app.post("/api/stop")
def stop_bot():
    """Stop the Naukri bot subprocess (backward-compatible endpoint)."""
    result = stop_platform_bot("naukri")

    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])

    return result


@app.get("/api/logs")
def get_logs(lines: int = 150):
    """Retrieve the last N lines of Naukri execution logs."""
    if not LOG_PATH.exists():
        return {"logs": "No logs recorded yet. Start the bot to generate logs."}

    try:
        with open(LOG_PATH, "r", encoding="utf-8") as fh:
            log_lines = fh.readlines()
            last_lines = log_lines[-lines:] if len(log_lines) > lines else log_lines
            return {"logs": "".join(last_lines)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read logs: {exc}")


@app.get("/api/results")
def get_results():
    """Retrieve all Naukri job-application results."""
    if not RESULTS_PATH.exists():
        return []

    try:
        with open(RESULTS_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


# ========================================================================
#  API — LinkedIn endpoints
# ========================================================================

@app.get("/api/linkedin/config")
def get_linkedin_config():
    """
    Read LinkedIn configuration from all 6 Python config files.

    Returns a dict keyed by config-file group (personals, questions,
    resume, search, secrets, settings) with nested variable dicts.
    """
    try:
        return read_all_linkedin_configs()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read LinkedIn config: {exc}")


@app.post("/api/linkedin/config")
def update_linkedin_config(data: LinkedInConfigModel):
    """
    Update LinkedIn configuration.

    Accepts a dict like:
        {"settings": {"personals": {"first_name": "Aditya"}, ...}}
    """
    try:
        summary = write_linkedin_configs(data.settings)
        return {
            "status": "success",
            "message": f"Updated {summary['updated']} variable(s).",
            "details": summary,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save LinkedIn config: {exc}")


@app.get("/api/linkedin/status")
def get_linkedin_status():
    """
    Get the LinkedIn bot's running status and basic stats from the CSV.
    """
    status = _get_platform_running_status("linkedin")

    # Compute stats from CSV
    csv_results = _parse_linkedin_results_csv()
    stats: Dict[str, Any] = {
        "total_applied": len(csv_results),
        "companies": len({r.get("Company", "") for r in csv_results if r.get("Company")}),
    }

    return {
        "running": status["running"],
        "pid": status["pid"],
        "elapsed_seconds": status["elapsed_seconds"],
        "stats": stats,
    }


@app.post("/api/linkedin/start")
def start_linkedin_bot():
    """Start the LinkedIn bot subprocess."""
    result = start_platform_bot("linkedin")
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@app.post("/api/linkedin/stop")
def stop_linkedin_bot():
    """Stop the LinkedIn bot subprocess."""
    result = stop_platform_bot("linkedin")
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@app.get("/api/linkedin/logs")
def get_linkedin_logs(lines: int = 150):
    """Retrieve the last N lines of LinkedIn bot execution logs."""
    log_path = Path(PLATFORMS["linkedin"]["log_path"])
    if not log_path.exists():
        return {"logs": "No LinkedIn logs recorded yet. Start the LinkedIn bot to generate logs."}

    try:
        with open(log_path, "r", encoding="utf-8") as fh:
            log_lines = fh.readlines()
            last_lines = log_lines[-lines:] if len(log_lines) > lines else log_lines
            return {"logs": "".join(last_lines)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read LinkedIn logs: {exc}")


@app.get("/api/linkedin/results")
def get_linkedin_results():
    """
    Parse the LinkedIn application-history CSV and return as a JSON array.

    Columns: Job_ID, Date_Applied, Title, Company, HR_Name, HR_Link,
    Job_Link, External_Job_link
    """
    try:
        return _parse_linkedin_results_csv()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read LinkedIn results: {exc}")


# ========================================================================
#  API — Scheduler endpoints
# ========================================================================

@app.get("/api/scheduler/status")
def api_scheduler_status():
    """Return the current scheduler status."""
    try:
        return get_scheduler_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to get scheduler status: {exc}")


@app.post("/api/scheduler/config")
def api_scheduler_config(data: SchedulerConfigModel):
    """
    Update the scheduler configuration.

    Accepts optional schedule_time (HH:MM) and enabled_platforms list.
    """
    try:
        result = update_scheduler_config(
            schedule_time=data.schedule_time,
            enabled_platforms=data.enabled_platforms,
        )
        return {"status": "success", "scheduler": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update scheduler config: {exc}")


@app.post("/api/scheduler/pause")
def api_scheduler_pause():
    """Pause the scheduler (the daily job will skip execution)."""
    try:
        return pause_scheduler()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to pause scheduler: {exc}")


@app.post("/api/scheduler/resume")
def api_scheduler_resume():
    """Resume the scheduler."""
    try:
        return resume_scheduler()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to resume scheduler: {exc}")


# ========================================================================
#  Main entry point
# ========================================================================

if __name__ == "__main__":
    print("Starting Job Automation Hub Backend on http://127.0.0.1:8000")
    uvicorn.run("backend:app", host="127.0.0.1", port=8000, reload=False)
