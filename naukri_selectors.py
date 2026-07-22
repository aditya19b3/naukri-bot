"""
naukri_selectors.py
-------------------
All CSS/XPath selectors for Naukri's UI live here, in one place.

Naukri periodically changes its front-end markup. When that happens, you
should only need to update the strings below -- no other module should
contain a hardcoded selector. Each selector includes a short comment
describing what it targets so future updates are easy.

Where reasonably possible, multiple fallback selectors are provided per
element (ordered from most to least specific) so the bot can survive minor
markup changes without breaking outright.
"""

from selenium.webdriver.common.by import By

# ---------------------------------------------------------------------
# Login page (https://www.naukri.com/nlogin/login)
# ---------------------------------------------------------------------
LOGIN_URL = "https://www.naukri.com/nlogin/login"

LOGIN_EMAIL_INPUT = (By.ID, "usernameField")
LOGIN_PASSWORD_INPUT = (By.ID, "passwordField")
LOGIN_SUBMIT_BUTTON = (By.XPATH, "//button[@type='submit']")

# Element(s) that only appear once login has succeeded. We check several
# because Naukri's home page markup differs by account state.
LOGIN_SUCCESS_INDICATORS = [
    (By.ID, "root"),  # the logged-in SPA root re-renders after login
    (By.XPATH, "//a[contains(@href,'/mnjuser/profile')]"),
    (By.XPATH, "//div[contains(@class,'nI-gNb-drawer__bar')]"),
]

# Error banner shown on bad credentials
LOGIN_ERROR_MESSAGE = (By.XPATH, "//span[contains(@class,'error-txt') or contains(text(),'Invalid')]")

# ---------------------------------------------------------------------
# Search results page
# ---------------------------------------------------------------------
SEARCH_BASE_URL = "https://www.naukri.com/{keyword}-jobs-in-{location}-{page}"
SEARCH_BASE_URL_NO_LOCATION = "https://www.naukri.com/{keyword}-jobs-{page}"

# Container that wraps the whole results list; used to know the page has
# rendered before we try to pull individual job cards out of it.
# Updated: Naukri changed to styles_jlc__main__VdwtF in their redesign
SEARCH_RESULTS_CONTAINER = (By.CLASS_NAME, "styles_jlc__main__VdwtF")

# Individual job card links. Naukri has used a couple of different class
# names for this over time, so we try a few.
JOB_CARD_LINK_SELECTORS = [
    (By.CSS_SELECTOR, "a.title"),
    (By.XPATH, "//div[contains(@class,'srp-jobtuple-wrapper')]//a[@class='title']"),
    (By.CSS_SELECTOR, "a.title.ellipsis"),
    (By.XPATH, "//a[contains(@class,'title') and @href]"),
]

# ---------------------------------------------------------------------
# Job detail page / apply flow
# ---------------------------------------------------------------------
APPLY_BUTTON_SELECTORS = [
    (By.ID, "apply-button"),
    (By.XPATH, "//button[contains(text(),'Apply') and not(contains(text(),'Applied'))]"),
]

ALREADY_APPLIED_INDICATORS = [
    (By.XPATH, "//*[contains(text(),'Already Applied') or contains(text(),'You have applied')]"),
]

# The "chatbot"-style quick apply modal that Naukri sometimes shows,
# requesting extra profile fields.
CHATBOT_MODAL = (By.CLASS_NAME, "chatbot_DrawerContentWrapper")
CHATBOT_INPUT_FIELD = (By.XPATH, "//div[contains(@class,'chatbot_DrawerContentWrapper')]//input")
CHATBOT_SUBMIT_BUTTON = (
    By.XPATH,
    "//div[contains(@class,'chatbot_DrawerContentWrapper')]//*[contains(text(),'Save') or contains(text(),'Submit')]",
)

# External-site redirect notice (application handled off Naukri's domain)
EXTERNAL_APPLY_INDICATOR = (By.XPATH, "//*[contains(text(),'redirected') or contains(text(),'company site')]")

# Daily application quota / limit message
DAILY_QUOTA_MESSAGE = (
    By.XPATH,
    "//*[contains(text(),'apply limit') or contains(text(),'daily limit') or contains(text(),'you have reached')]",
)

# Generic first/last name fields that occasionally appear in quick-apply forms
FIRST_NAME_INPUT = (By.XPATH, "//input[contains(@name,'first') or contains(@id,'first')]")
LAST_NAME_INPUT = (By.XPATH, "//input[contains(@name,'last') or contains(@id,'last')]")

# Chatbot conversational flow selectors
CHATBOT_QUESTION_TEXT = (
    By.XPATH,
    "(//div[contains(@class, 'botMsg') or contains(@class, 'bot-msg')] | //li[contains(@class, 'botItem')])[last()]"
)
CHATBOT_TEXT_INPUT = (
    By.XPATH,
    "//div[@contenteditable='true' and contains(@class, 'textArea')] | //textarea[contains(@class, 'textArea')] | //input[@type='text' and contains(@class, 'chat-input')] | //input[not(@type) or @type='text' or @type='number']"
)
CHATBOT_SEND_BUTTON = (
    By.XPATH,
    "//button[contains(text(), 'Send') or contains(text(), 'send') or contains(@class, 'send')] | //span[@class='chatBot' and contains(@class, 'send')] | //i[@class='add-icon']//parent::span | //span[contains(@class, 'send')] | //button[@type='button' and contains(@class, 'send')]"
)
CHATBOT_OPTION_BUTTONS = (
    By.XPATH,
    "//div[contains(@class, 'option') or contains(@class, 'chip') or contains(@class, 'pill')]//button | //div[contains(@class, 'option') or contains(@class, 'chip') or contains(@class, 'pill')]//span | //ul[contains(@class, 'options') or contains(@class, 'chips')]/li | //span[contains(@class, 'chip') or contains(@class, 'pill')] | //button[contains(@class, 'chip') or contains(@class, 'pill')]"
)
CHATBOT_MESSAGES_CONTAINER = (
    By.XPATH,
    "//div[contains(@class, 'chatBot') or contains(@class, 'chat-container') or contains(@class, 'messages')]"
)

