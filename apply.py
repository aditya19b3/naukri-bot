"""
apply.py
--------
Visits individual job pages and attempts to apply, handling quick-apply
forms, already-applied states, external redirects, and daily quota limits.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, TYPE_CHECKING
if TYPE_CHECKING:
    from ai_answerer import ChatbotAnswerer

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import naukri_selectors as sel
from utils import human_delay, logger


class ApplyStatus(str, Enum):
    APPLIED = "APPLIED"
    ALREADY_APPLIED = "ALREADY_APPLIED"
    EXTERNAL_REDIRECT = "EXTERNAL_REDIRECT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class QuotaExceededError(Exception):
    """Raised when Naukri reports the daily application limit has been hit."""


class NaukriJobApply:
    def __init__(self, driver: WebDriver, first_name: str, last_name: str, wait_timeout: int = 15, answerer: ChatbotAnswerer | None = None):
        self.driver = driver
        self.first_name = first_name
        self.last_name = last_name
        self.wait = WebDriverWait(driver, wait_timeout)
        self.answerer = answerer


    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _element_exists(self, locators) -> bool:
        """Return True if any locator in a list of (By, value) tuples matches an element."""
        if isinstance(locators, tuple):
            locators = [locators]
        for locator in locators:
            try:
                if self.driver.find_elements(*locator):
                    return True
            except (NoSuchElementException, StaleElementReferenceException):
                continue
        return False

    def _check_daily_quota(self) -> None:
        if self._element_exists(sel.DAILY_QUOTA_MESSAGE):
            raise QuotaExceededError("Naukri reported the daily application limit has been reached.")

    def _fill_quick_apply_form(self) -> None:
        """
        If Naukri pops up a quick-apply / chatbot drawer asking for extra
        profile fields, fill in the basics we know (first/last name),
        auto-fill year fields with "3", and select "yes" for choice questions.
        Handles both traditional form inputs and chatbot-style contenteditable inputs.
        """
        try:
            WebDriverWait(self.driver, 4).until(EC.presence_of_element_located(sel.CHATBOT_MODAL))
        except TimeoutException:
            return  # No extra form appeared; nothing to fill.

        logger.info("Quick-apply form detected; attempting to fill known fields.")
        try:
            # Strategy 1: Handle chatbot-style contenteditable inputs
            try:
                self._handle_chatbot_questions()
            except Exception as e:
                logger.debug("Chatbot input handling failed: %s", e)
            
            human_delay(0.5, 1.0)

            # Strategy 2: Handle traditional form fields (first name, last name)
            first_field = self.driver.find_elements(*sel.FIRST_NAME_INPUT)
            if first_field:
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", first_field[0])
                    WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable((type(first_field[0]), first_field[0].get_attribute("name") or first_field[0].get_attribute("id"))))
                    first_field[0].clear()
                    first_field[0].send_keys(self.first_name)
                    logger.info("Filled first name field")
                except Exception as e:
                    logger.debug("Could not fill first name: %s", e)

            last_field = self.driver.find_elements(*sel.LAST_NAME_INPUT)
            if last_field:
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", last_field[0])
                    last_field[0].clear()
                    last_field[0].send_keys(self.last_name)
                    logger.info("Filled last name field")
                except Exception as e:
                    logger.debug("Could not fill last name: %s", e)

            human_delay(0.5, 1.0)

            # Strategy 3: Auto-fill year fields with "3"
            try:
                year_inputs = self.driver.find_elements(By.XPATH, 
                    "//div[contains(@class, 'chatbot') or contains(@class, 'drawer') or contains(@class, 'modal')]//input[@type='text' or @type='number' or not(@type)] | "
                    "//input[contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'year') or contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'experience')] | "
                    "//input[contains(translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'year') or contains(translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'experience')] | "
                    "//input[@type='number']")
                
                filled_count = 0
                for year_field in year_inputs:
                    try:
                        if year_field.is_displayed():
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", year_field)
                            human_delay(0.2, 0.4)
                            year_field.clear()
                            try:
                                year_field.send_keys("3")
                            except Exception:
                                self.driver.execute_script("arguments[0].value = '3'; arguments[0].dispatchEvent(new Event('input', { bubbles: true })); arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", year_field)
                            logger.info("Filled year/experience field with '3'")
                            filled_count += 1
                            if filled_count >= 3:
                                break
                    except Exception as e:
                        logger.debug("Could not fill individual year field: %s", e)
            except Exception as e:
                logger.debug("Could not fill year fields: %s", e)

            human_delay(0.5, 1.0)

            # Strategy 4: Auto-select "yes" for choice/radio buttons
            try:
                yes_labels = self.driver.find_elements(By.XPATH, "//label[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'yes')]")
                for label in yes_labels[:5]:
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", label)
                        human_delay(0.2, 0.4)
                        label.click()
                        logger.info("Selected 'Yes' option")
                    except Exception:
                        pass
                
                yes_options = self.driver.find_elements(By.XPATH, "//input[@value='yes' or @value='Yes' or @value='YES']")
                for yes_btn in yes_options[:5]:
                    try:
                        if yes_btn.is_displayed() and not yes_btn.is_selected():
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", yes_btn)
                            human_delay(0.2, 0.4)
                            yes_btn.click()
                            logger.info("Selected 'Yes' option via value")
                    except Exception:
                        pass
            except Exception as e:
                logger.debug("Could not select yes options: %s", e)

            human_delay(0.5, 1.5)

            submit_btns = self.driver.find_elements(*sel.CHATBOT_SUBMIT_BUTTON)
            if submit_btns:
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", submit_btns[0])
                    WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable(sel.CHATBOT_SUBMIT_BUTTON))
                    submit_btns[0].click()
                    logger.info("Clicked submit button")
                except Exception as e:
                    logger.debug("Could not click submit button: %s", e)
        except (NoSuchElementException, StaleElementReferenceException) as exc:
            logger.warning("Could not fully complete quick-apply form: %s", exc)

    def _handle_chatbot_questions(self) -> None:
        """
        Handle chatbot-style conversational Q&A flow sequentially using AI.
        """
        if not self.answerer:
            logger.warning("No ChatbotAnswerer provided; using minimal fallback flow.")
            
        max_iterations = 15
        prev_question_text = ""
        repeated_question_count = 0
        
        logger.info("Entering conversational chatbot Q&A loop.")
        
        for iteration in range(1, max_iterations + 1):
            logger.info("Chatbot Q&A loop iteration %d/%d", iteration, max_iterations)
            
            # Check if chatbot drawer is still open/present
            if not self._element_exists(sel.CHATBOT_MODAL):
                logger.info("Chatbot modal/drawer is no longer present. Exiting Q&A loop.")
                break
                
            # Extract latest question text
            question_elems = self.driver.find_elements(*sel.CHATBOT_QUESTION_TEXT)
            question_text = ""
            if question_elems:
                try:
                    question_text = question_elems[-1].text.strip()
                except Exception:
                    pass
            
            logger.info("Extracted latest question: '%s'", question_text)
            
            # Check if we are stuck on the same question
            if question_text == prev_question_text:
                repeated_question_count += 1
                if repeated_question_count >= 3:
                    logger.warning("Stuck on the same question '%s' for 3 iterations. Exiting loop to avoid infinite loop.", question_text)
                    break
            else:
                repeated_question_count = 0
                prev_question_text = question_text
                
            # Check if there are options / chips available to click
            option_elems = self.driver.find_elements(*sel.CHATBOT_OPTION_BUTTONS)
            visible_options = []
            for elem in option_elems:
                try:
                    if elem.is_displayed() and elem.text.strip():
                        visible_options.append((elem.text.strip(), elem))
                except Exception:
                    pass
                    
            if visible_options:
                option_texts = [opt[0] for opt in visible_options]
                logger.info("Found %d visible option chips: %s", len(visible_options), option_texts)
                
                # Get the answer from our answerer
                if self.answerer:
                    answer = self.answerer.answer_question(question_text, option_texts)
                else:
                    answer = option_texts[0]
                    
                # Find matching option element (exact or substring match)
                matching_elem = None
                for opt_text, elem in visible_options:
                    if answer.lower() == opt_text.lower():
                        matching_elem = elem
                        break
                if not matching_elem:
                    # Fallback to closest match
                    for opt_text, elem in visible_options:
                        if answer.lower() in opt_text.lower() or opt_text.lower() in answer.lower():
                            matching_elem = elem
                            break
                if not matching_elem:
                    # Fallback to the first option
                    matching_elem = visible_options[0][1]
                    logger.warning("Could not find matching option for answer '%s'. Defaulting to option '%s'.", answer, visible_options[0][0])
                    
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", matching_elem)
                    human_delay(0.3, 0.6)
                    # Extract text before clicking to avoid StaleElementReferenceException
                    opt_text_clicked = "Unknown"
                    try:
                        opt_text_clicked = matching_elem.text.strip()
                    except Exception:
                        pass
                    
                    try:
                        matching_elem.click()
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", matching_elem)
                        
                    logger.info("Clicked option button: '%s'", opt_text_clicked)
                    human_delay(1.5, 2.5)
                    continue
                except Exception as e:
                    logger.debug("Failed to click option element: %s. Trying text input strategy.", e)

            
            # Check for text inputs (contenteditable or standard input)
            input_elems = self.driver.find_elements(*sel.CHATBOT_TEXT_INPUT)
            active_input = None
            for elem in input_elems:
                try:
                    if elem.is_displayed() and elem.is_enabled():
                        # Make sure it's not a button or submit element
                        tag_name = elem.tag_name.lower()
                        if tag_name == "input" and elem.get_attribute("type") in {"submit", "button", "radio", "checkbox"}:
                            continue
                        active_input = elem
                        break
                except Exception:
                    pass
                    
            if active_input:
                # Generate text answer
                if self.answerer:
                    answer = self.answerer.answer_question(question_text)
                else:
                    answer = "3"
                    
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", active_input)
                    human_delay(0.3, 0.6)
                    active_input.click()
                    human_delay(0.2, 0.4)
                    
                    # Clear input
                    tag_name = active_input.tag_name.lower()
                    is_contenteditable = active_input.get_attribute("contenteditable") == "true"
                    
                    if is_contenteditable:
                        # Clear contenteditable
                        self.driver.execute_script("arguments[0].innerHTML = '';", active_input)
                    else:
                        active_input.clear()
                        
                    active_input.send_keys(answer)
                    logger.info("Typed answer: '%s'", answer)
                    human_delay(0.4, 0.8)
                    
                    # Click send button
                    send_buttons = self.driver.find_elements(*sel.CHATBOT_SEND_BUTTON)
                    sent = False
                    for send_btn in send_buttons:
                        try:
                            if send_btn.is_displayed():
                                self.driver.execute_script("arguments[0].scrollIntoView(true);", send_btn)
                                human_delay(0.2, 0.4)
                                try:
                                    send_btn.click()
                                except Exception:
                                    self.driver.execute_script("arguments[0].click();", send_btn)
                                logger.info("Clicked send button.")
                                sent = True
                                break
                        except Exception:
                            pass

                            
                    if not sent:
                        # Fallback to pressing enter
                        active_input.send_keys("\n")
                        logger.info("Pressed Enter to submit answer.")
                        
                    human_delay(1.5, 2.5)
                    continue
                except Exception as e:
                    logger.debug("Failed to handle text input: %s", e)
                    
            submit_btns = self.driver.find_elements(*sel.CHATBOT_SUBMIT_BUTTON)
            if submit_btns:
                try:
                    btn = submit_btns[0]
                    if btn.is_displayed() and btn.is_enabled():
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                        human_delay(0.3, 0.6)
                        try:
                            btn.click()
                        except Exception:
                            self.driver.execute_script("arguments[0].click();", btn)
                        logger.info("Clicked chatbot submit/save button.")
                        human_delay(1.5, 2.5)
                        continue
                except Exception:
                    pass

            
            # If no input or option buttons were found, wait a bit and retry
            logger.info("No active input/options found in this iteration. Waiting for updates...")
            human_delay(1.5, 2.5)
            
        logger.info("Exited chatbot conversational loop.")


    def apply_to_job(self, job_url: str) -> Dict[str, str]:
        """
        Attempt to apply to a single job. Returns a result dict with keys:
        job_url, status, timestamp, error_message, external_link.
        """
        result = {
            "job_url": job_url,
            "status": ApplyStatus.FAILED.value,
            "timestamp": self._timestamp(),
            "error_message": "",
            "external_link": "",  # For company websites that need manual filling
        }

        try:
            self.driver.get(job_url)
            human_delay(1.5, 3.0)

            self._check_daily_quota()

            if self._element_exists(sel.ALREADY_APPLIED_INDICATORS):
                result["status"] = ApplyStatus.ALREADY_APPLIED.value
                logger.info("Already applied: %s", job_url)
                return result

            apply_btn = None
            for locator in sel.APPLY_BUTTON_SELECTORS:
                try:
                    apply_btn = self.wait.until(EC.element_to_be_clickable(locator))
                    break
                except TimeoutException:
                    continue

            if apply_btn is None:
                result["status"] = ApplyStatus.SKIPPED.value
                result["error_message"] = "No Apply button found on page."
                logger.warning("No apply button found for %s", job_url)
                return result

            try:
                apply_btn.click()
            except ElementClickInterceptedException:
                self.driver.execute_script("arguments[0].click();", apply_btn)

            human_delay(1.5, 3.0)

            self._check_daily_quota()

            # Check for external redirect and capture the external link
            if self._element_exists(sel.EXTERNAL_APPLY_INDICATOR):
                result["status"] = ApplyStatus.EXTERNAL_REDIRECT.value
                # Try to capture the company website link from the page
                try:
                    company_link_elem = self.driver.find_elements("XPATH", "//a[contains(text(), 'company') or contains(text(), 'Company')]")
                    if company_link_elem:
                        result["external_link"] = company_link_elem[0].get_attribute("href") or ""
                except Exception:
                    pass
                logger.info("External redirect apply (not fully automatable): %s", job_url)
                return result

            self._fill_quick_apply_form()

            self._check_daily_quota()

            result["status"] = ApplyStatus.APPLIED.value
            logger.info("Successfully applied: %s", job_url)
            return result

        except QuotaExceededError:
            raise  # propagate up so the caller can stop the whole run gracefully
        except TimeoutException as exc:
            result["error_message"] = f"Timed out waiting for page elements: {exc}"
            logger.error("Timeout applying to %s: %s", job_url, exc)
        except Exception as exc:  # noqa: BLE001 - log and continue, never crash the run
            result["error_message"] = str(exc)
            logger.error("Failed to apply to %s: %s", job_url, exc)

        return result
