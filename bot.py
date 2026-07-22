"""
bot.py
------
Top-level orchestrator that wires together login, search, and apply
into a single run, tracking results as it goes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from selenium.webdriver.remote.webdriver import WebDriver

from apply import ApplyStatus, NaukriJobApply, QuotaExceededError
from config import Config
from login import LoginError, NaukriLogin
from search import NaukriJobSearch
from utils import human_delay, logger
from ai_answerer import ChatbotAnswerer



class NaukriBot:
    def __init__(self, driver: WebDriver, config: Config):
        self.driver = driver
        self.config = config
        self.answerer = ChatbotAnswerer(self.config)
        self.results: List[Dict[str, str]] = []
        self._quota_hit = False


    def run(self) -> List[Dict[str, str]]:
        """Execute the full pipeline: login -> search -> apply. Returns result list."""
        self._login()
        job_links = self._discover_jobs()
        self._apply_to_jobs(job_links)
        return self.results

    # ------------------------------------------------------------------
    def _login(self) -> None:
        login_handler = NaukriLogin(self.driver, wait_timeout=self.config.wait_timeout)
        try:
            login_handler.login(self.config.email, self.config.password)
        except LoginError as exc:
            logger.error("LOGIN FAILED: %s", exc)
            raise SystemExit(1) from exc

    # ------------------------------------------------------------------
    def _discover_jobs(self) -> List[str]:
        searcher = NaukriJobSearch(self.driver, wait_timeout=self.config.wait_timeout)
        all_links: List[str] = []
        seen = set()

        for keyword in self.config.keywords:
            logger.info("=== Searching keyword: '%s' ===", keyword)
            links = searcher.search_jobs(keyword, self.config.location, self.config.pages_per_keyword)
            for link in links:
                if link not in seen:
                    seen.add(link)
                    all_links.append(link)
            human_delay(self.config.min_delay, self.config.max_delay)

        logger.info("Discovered %d unique job links across all keywords.", len(all_links))
        return all_links

    # ------------------------------------------------------------------
    def _apply_to_jobs(self, job_links: List[str]) -> None:
        applier = NaukriJobApply(
            self.driver,
            first_name=self.config.first_name,
            last_name=self.config.last_name,
            wait_timeout=self.config.wait_timeout,
            answerer=self.answerer,
        )


        applied_count = 0
        for job_url in job_links:
            if applied_count >= self.config.max_applications:
                logger.info("Reached max_applications limit (%d); stopping.", self.config.max_applications)
                break

            try:
                result = applier.apply_to_job(job_url)
            except QuotaExceededError as exc:
                logger.warning("Stopping run: %s", exc)
                self._quota_hit = True
                break

            self.results.append(result)

            if result["status"] == ApplyStatus.APPLIED.value:
                applied_count += 1

            human_delay(self.config.min_delay, self.config.max_delay)

    # ------------------------------------------------------------------
    def summary(self) -> Dict[str, int]:
        applied = sum(1 for r in self.results if r["status"] == ApplyStatus.APPLIED.value)
        already_applied = sum(1 for r in self.results if r["status"] == ApplyStatus.ALREADY_APPLIED.value)
        external = sum(1 for r in self.results if r["status"] == ApplyStatus.EXTERNAL_REDIRECT.value)
        skipped = sum(1 for r in self.results if r["status"] == ApplyStatus.SKIPPED.value)
        failed = sum(1 for r in self.results if r["status"] == ApplyStatus.FAILED.value)
        return {
            "applied": applied,
            "already_applied": already_applied,
            "external_redirect": external,
            "skipped": skipped,
            "failed": failed,
            "total": len(self.results),
            "quota_hit": self._quota_hit,
        }
