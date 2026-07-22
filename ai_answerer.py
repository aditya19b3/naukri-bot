"""
ai_answerer.py
--------------
AI-powered answer generator for Naukri recruiter chatbot questions.
Uses Codex/OpenAI Chat Completions API with a robust rule-based fallback mechanism.
"""

from __future__ import annotations

import re
import json
import urllib.request
import urllib.error
from typing import List
from config import Config
from utils import logger


class ChatbotAnswerer:
    def __init__(self, config: Config):
        self.config = config
        self.api_initialized = False

        if not self.config.codex_api_key:
            logger.warning("CODEX_API_KEY is not configured in environment. Using rule-based fallback answering.")
            return

        self.api_initialized = True
        logger.info("Codex AI Answerer initialized successfully using endpoint: %s", self.config.codex_api_base_url)

    def answer_question(self, question: str, options: List[str] | None = None) -> str:
        """
        Generate a concise answer for a chatbot question.
        Falls back to rule-based answering if Codex is unavailable or fails.
        """
        clean_question = question.strip()
        if not clean_question:
            return ""

        logger.info("Answering chatbot question: '%s'", clean_question)
        if options:
            logger.info("Question options: %s", options)

        # Attempt to get answer via Codex / OpenAI API
        if self.api_initialized and self.config.codex_api_key:
            try:
                prompt = self._build_prompt(clean_question, options)
                
                # Payload for Chat Completions API
                payload = {
                    "model": self.config.codex_model or "gpt-4o-mini",
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 150
                }
                
                # Convert payload to bytes
                data = json.dumps(payload).encode("utf-8")
                
                # Setup request
                req = urllib.request.Request(
                    self.config.codex_api_base_url,
                    data=data,
                    headers={
                        "Authorization": f"Bearer {self.config.codex_api_key}",
                        "Content-Type": "application/json"
                    },
                    method="POST"
                )
                
                # Execute request with timeout
                with urllib.request.urlopen(req, timeout=10) as response:
                    res_body = response.read().decode("utf-8")
                    res_json = json.loads(res_body)
                    
                    # Extract answer from response
                    choices = res_json.get("choices", [])
                    if choices:
                        answer = choices[0].get("message", {}).get("content", "").strip()
                        if answer:
                            logger.info("Codex AI answered: '%s'", answer)
                            # Clean up quotes if returned by model
                            if (answer.startswith('"') and answer.endswith('"')) or (answer.startswith("'") and answer.endswith("'")):
                                answer = answer[1:-1].strip()
                            return answer
            except Exception as e:
                logger.error("Codex AI content generation failed: %s. Using fallback.", e)

        # Fallback to rule-based matching
        fallback_ans = self._get_fallback_answer(clean_question, options)
        logger.info("Fallback answered: '%s'", fallback_ans)
        return fallback_ans

    def _build_prompt(self, question: str, options: List[str] | None = None) -> str:
        """Build a detailed system prompt with applicant profile context."""
        context = (
            f"Applicant Profile Context:\n"
            f"- First Name: {self.config.first_name}\n"
            f"- Last Name: {self.config.last_name}\n"
            f"- Total Years of Experience: {self.config.years_of_experience}\n"
            f"- Current CTC: {self.config.current_ctc}\n"
            f"- Expected CTC: {self.config.expected_ctc}\n"
            f"- Notice Period: {self.config.notice_period}\n"
            f"- Skills: {self.config.skills}\n"
            f"- Current Location: {self.config.current_location}\n"
            f"- Preferred Locations: {self.config.preferred_locations}\n"
            f"- Gender: {self.config.gender}\n"
            f"- Graduation Year: {self.config.graduation_year}\n"
            f"- Highest Qualification: {self.config.highest_qualification}\n"
            f"- Current Company: {self.config.current_company}\n"
            f"- Work Authorization: {self.config.work_authorization}\n"
            f"- Shift Flexibility: {self.config.shift_flexibility}\n"
        )

        instructions = (
            "You are answering a chatbot questionnaire on a job application portal on behalf of the applicant.\n"
            "Generate a professional, accurate, and extremely concise answer to the question using the profile context.\n"
            "CRITICAL RULES:\n"
            "1. If the question asks for a number (like years of experience, or notice period in days), reply with ONLY the number. Do not include any words.\n"
            "2. If the question is multiple choice, select the best matching option from the choices list. Reply with ONLY the exact option text.\n"
            "3. Keep written/text responses extremely short (1 sentence or a short phrase, max 10 words).\n"
            "4. Do NOT say 'Here is the answer:', 'Based on your profile...', or include any conversational filler. Just output the final response.\n"
            "5. If the question asks about years of experience (whether total/overall/relevant experience or experience in a specific technology/skill like Java, Python, Gen AI, React, etc.), always answer with '3' (or choose the exact multiple-choice option corresponding to 3 years).\n"
        )

        if options:
            options_text = ", ".join(f"'{opt}'" for opt in options)
            prompt = (
                f"{context}\n"
                f"{instructions}\n"
                f"Question: {question}\n"
                f"Available Options: [{options_text}]\n"
                f"Answer:"
            )
        else:
            prompt = (
                f"{context}\n"
                f"{instructions}\n"
                f"Question: {question}\n"
                f"Answer:"
            )
        return prompt

    def _get_fallback_answer(self, question: str, options: List[str] | None = None) -> str:
        """Rule-based question answering when API is unavailable."""
        q_lower = question.lower()

        # Handle multiple choice options first
        if options:
            # 1. If notice period question
            if "notice" in q_lower or "join" in q_lower:
                # Try to match config notice period first
                config_np_digits = re.findall(r'\d+', self.config.notice_period.lower())
                if config_np_digits:
                    for opt in options:
                        for digit in config_np_digits:
                            if digit in opt:
                                return opt
                # Fallback to standard check
                for opt in options:
                    o_lower = opt.lower()
                    if "30" in o_lower or "15" in o_lower or "immediate" in o_lower or "serving" in o_lower:
                        return opt
                return options[0]

            # 2. If relocation question
            if "relocate" in q_lower or "location" in q_lower:
                for opt in options:
                    if opt.lower() in {"yes", "sure", "relocate"}:
                        return opt
                return options[0]

            # 3. Numeric or experience options
            if "experience" in q_lower or "years" in q_lower or re.search(r'\bexp\b', q_lower):
                # Always answer with 3 for any experience question
                for opt in options:
                    if "3" in opt:
                        return opt
                # Fallback to configured experience digit matching
                exp_digits = re.findall(r'\d+', self.config.years_of_experience)
                if exp_digits:
                    num = exp_digits[0]
                    for opt in options:
                        if num in opt:
                            return opt
                return options[0]

            # 4. Gender
            if "gender" in q_lower:
                for opt in options:
                    if self.config.gender.lower() in opt.lower():
                        return opt
                return options[0]

            # 5. Graduation Year
            if "graduation" in q_lower or "passing year" in q_lower or "passed out" in q_lower:
                for opt in options:
                    if self.config.graduation_year in opt:
                        return opt
                return options[0]

            # 6. Education / Qualification
            if "qualification" in q_lower or "degree" in q_lower or "education" in q_lower:
                for opt in options:
                    if self.config.highest_qualification.lower() in opt.lower():
                        return opt
                return options[0]

            # 7. Work Authorization / Visa / Citizenship
            if "visa" in q_lower or "authorize" in q_lower or "citizen" in q_lower or "eligible" in q_lower or "sponsorship" in q_lower:
                is_yes = self.config.work_authorization.lower() in {"yes", "true", "1", "authorized"}
                for opt in options:
                    o_lower = opt.lower()
                    if is_yes and o_lower in {"yes", "sure", "relocate"}:
                        return opt
                    if not is_yes and o_lower in {"no"}:
                        return opt
                return options[0]

            # 8. Shift Flexibility
            if "shift" in q_lower or "night" in q_lower or "hours" in q_lower:
                is_yes = self.config.shift_flexibility.lower() in {"yes", "true", "1"}
                for opt in options:
                    o_lower = opt.lower()
                    if is_yes and o_lower in {"yes", "sure"}:
                        return opt
                    if not is_yes and o_lower in {"no"}:
                        return opt
                return options[0]

            # 9. Skill ratings or numerical scales (out of 10)
            if "rate" in q_lower or "scale" in q_lower or "out of" in q_lower:
                for num in ["8", "9", "7", "10", "5"]:
                    for opt in options:
                        if opt.strip() == num:
                            return opt
                return options[-1]

            # Default to first option
            return options[0]

        # Handle text responses (No options)
        # Check CTC first to avoid "exp" prefix match in "expected"
        if "expected ctc" in q_lower or "expected salary" in q_lower or "expectation" in q_lower:
            return self.config.expected_ctc or "12 LPA"
        if "current ctc" in q_lower or "current salary" in q_lower or "ctc" in q_lower:
            return self.config.current_ctc or "8 LPA"

        # Notice period questions
        if "notice" in q_lower or "join" in q_lower:
            return self.config.notice_period or "30 days"

        # Experience questions (checking "exp" as word boundary or after others)
        if "experience" in q_lower or "years" in q_lower or re.search(r'\bexp\b', q_lower):
            # Always return "3" for any experience question
            return "3"

        # Location questions
        if "location" in q_lower or "city" in q_lower:
            if "preferred" in q_lower or "preference" in q_lower:
                return self.config.preferred_locations.split(",")[0].strip()
            return self.config.current_location or "Bangalore"

        # Relocation questions
        if "relocate" in q_lower:
            return "Yes"

        # Gender questions
        if "gender" in q_lower:
            return self.config.gender

        # Graduation year questions
        if "graduation" in q_lower or "passing year" in q_lower or "passed out" in q_lower:
            return self.config.graduation_year

        # Qualification / Education questions
        if "qualification" in q_lower or "degree" in q_lower or "education" in q_lower:
            return self.config.highest_qualification

        # Current Company
        if "current company" in q_lower or "current employer" in q_lower or "organization" in q_lower:
            return self.config.current_company or "Self Employed"

        # Work authorization
        if "visa" in q_lower or "authorize" in q_lower or "citizen" in q_lower or "eligible" in q_lower or "sponsorship" in q_lower:
            return self.config.work_authorization

        # Shift flexibility
        if "shift" in q_lower or "night" in q_lower:
            return self.config.shift_flexibility

        # Rating scale text
        if "rate" in q_lower or "scale" in q_lower or "out of" in q_lower:
            return "8"

        # Skill / Tools questions
        skills_list = [s.strip().lower() for s in self.config.skills.split(",")]
        for skill in skills_list:
            if skill and skill in q_lower:
                return "Yes"

        # General default fallback
        return "Yes"

