"""
login.py
--------
Handles authenticating into Naukri.com.
"""

from __future__ import annotations

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import naukri_selectors as sel
from utils import human_delay, logger


class LoginError(Exception):
    """Raised when login fails for any reason."""


class NaukriLogin:
    def __init__(self, driver: WebDriver, wait_timeout: int = 15):
        self.driver = driver
        self.wait = WebDriverWait(driver, wait_timeout)

    def login(self, email: str, password: str) -> None:
        """
        Log into Naukri using the given credentials.
        Raises LoginError with a clear message if login does not succeed.
        """
        logger.info("Navigating to Naukri login page...")
        self.driver.get(sel.LOGIN_URL)

        try:
            email_field = self.wait.until(EC.presence_of_element_located(sel.LOGIN_EMAIL_INPUT))
            password_field = self.wait.until(EC.presence_of_element_located(sel.LOGIN_PASSWORD_INPUT))
        except TimeoutException as exc:
            raise LoginError(
                "Login form did not load in time. Naukri's page structure may "
                "have changed -- check selectors.LOGIN_EMAIL_INPUT / LOGIN_PASSWORD_INPUT."
            ) from exc

        email_field.clear()
        email_field.send_keys(email)
        human_delay(0.5, 1.2)

        password_field.clear()
        password_field.send_keys(password)
        human_delay(0.5, 1.2)

        try:
            submit_button = self.wait.until(EC.element_to_be_clickable(sel.LOGIN_SUBMIT_BUTTON))
            submit_button.click()
        except TimeoutException as exc:
            raise LoginError("Could not find/click the login submit button.") from exc

        logger.info("Submitted login form, waiting for confirmation...")
        self._wait_for_login_result()

    def _wait_for_login_result(self) -> None:
        """Wait for either a success indicator or an error message to appear."""
        # First, check quickly for an explicit error banner (bad credentials).
        try:
            error_el = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(sel.LOGIN_ERROR_MESSAGE)
            )
            if error_el and error_el.text.strip():
                raise LoginError(f"Naukri reported a login error: {error_el.text.strip()}")
        except TimeoutException:
            pass  # No error banner shown; continue checking for success.

        # Then wait for any of the known "logged in" indicators.
        for locator in sel.LOGIN_SUCCESS_INDICATORS:
            try:
                self.wait.until(EC.presence_of_element_located(locator))
                logger.info("Login successful.")
                return
            except TimeoutException:
                continue

        raise LoginError(
            "Could not confirm successful login. This may mean the credentials "
            "are wrong, a CAPTCHA/OTP step appeared, or Naukri's page structure changed."
        )
