"""
search.py
---------
Builds Naukri search URLs, loads result pages, and extracts unique job links.
"""

from __future__ import annotations

import re
from typing import List, Set

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import naukri_selectors as sel
from utils import human_delay, logger, retry


def _slugify(text: str) -> str:
    """Convert a free-text keyword/location into Naukri's URL-slug format."""
    text = text.strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9\-]", "", text)
    return text


class NaukriJobSearch:
    def __init__(self, driver: WebDriver, wait_timeout: int = 15):
        self.driver = driver
        self.wait = WebDriverWait(driver, wait_timeout)

    def build_search_url(self, keyword: str, location: str, page: int = 1) -> str:
        keyword_slug = _slugify(keyword)
        if location:
            location_slug = _slugify(location)
            suffix = f"-{page}" if page > 1 else ""
            return f"https://www.naukri.com/{keyword_slug}-jobs-in-{location_slug}{suffix}"
        suffix = f"-{page}" if page > 1 else ""
        return f"https://www.naukri.com/{keyword_slug}-jobs{suffix}"

    @retry(times=3, delay=2.0, exceptions=(TimeoutException,))
    def _load_results_page(self, url: str) -> None:
        logger.info("Loading search results page: %s", url)
        self.driver.get(url)
        self.wait.until(EC.presence_of_element_located(sel.SEARCH_RESULTS_CONTAINER))

    def extract_job_links(self) -> List[str]:
        """Pull all job-detail links off the currently loaded results page."""
        links: Set[str] = set()
        for locator in sel.JOB_CARD_LINK_SELECTORS:
            elements = self.driver.find_elements(*locator)
            for el in elements:
                href = el.get_attribute("href")
                if href:
                    links.add(href.split("?")[0])  # strip tracking params
            if links:
                break  # stop once one selector strategy has produced results
        logger.info("Extracted %d job links from this page.", len(links))
        return list(links)

    def search_jobs(self, keyword: str, location: str, pages: int = 1) -> List[str]:
        """Search for a keyword across `pages` result pages, returning deduped links."""
        all_links: Set[str] = set()

        for page in range(1, pages + 1):
            url = self.build_search_url(keyword, location, page)
            try:
                self._load_results_page(url)
            except TimeoutException:
                logger.warning(
                    "Search results did not load for '%s' page %d (selector may be stale). Skipping page.",
                    keyword,
                    page,
                )
                continue

            page_links = self.extract_job_links()
            if not page_links:
                logger.info("No more results found for '%s' at page %d; stopping pagination.", keyword, page)
                break

            all_links.update(page_links)
            human_delay(2, 4)

        logger.info("Total unique links found for keyword '%s': %d", keyword, len(all_links))
        return list(all_links)
