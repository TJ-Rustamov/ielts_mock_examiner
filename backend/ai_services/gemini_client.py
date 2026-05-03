import os
from typing import Any

from ai_services.prompts import (
    IELTS_EXAMINER_PROMPT,
    IELTS_EXAMINER_PROMPT_PART1,
    IELTS_EXAMINER_PROMPT_PART2,
    IELTS_EXAMINER_PROMPT_PART3,
    IELTS_TASK_1_EXAMINER_PROMPT,
    IELTS_TASK_2_EXAMINER_PROMPT,
)
from ai_services.utils import average_score, extract_json_from_text


class GeminiClient:
    """Gemini wrapper with separate speaking/writing models and low-cost generation config."""

    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.enabled = bool(self.api_key)
        self.client = None
        self._types = None

        self.speaking_model_name = os.getenv("GEMINI_SPEAKING_MODEL", "gemini-3.1-flash-lite-preview")
        self.writing_model_name = os.getenv("GEMINI_WRITING_MODEL", self.speaking_model_name)

        self.generation_config = {
            "temperature": float(os.getenv("GEMINI_TEMPERATURE", "0.2")),
            "top_p": float(os.getenv("GEMINI_TOP_P", "0.8")),
            "candidate_count": 1,
        }

        # Allow admin-configured models/temperature when DB is available.
        try:
            from core.models import AIConfiguration

            cfg = AIConfiguration.objects.first()
            if cfg:
                enabled = cfg.enabled_models or []
                self.speaking_model_name = cfg.speaking_model or self.speaking_model_name
                self.writing_model_name = cfg.writing_model or self.writing_model_name
                if enabled:
                    if self.speaking_model_name not in enabled:
                        self.speaking_model_name = enabled[0]
                    if self.writing_model_name not in enabled:
                        self.writing_model_name = enabled[0]
                self.generation_config["temperature"] = float(cfg.temperature)
        except Exception:
            # Keep environment-based defaults when DB is unavailable (startup/migrations).
            pass

        if self.enabled:
            self.speaking_model = self.speaking_model_name
            self.writing_model = self.writing_model_name
        else:
            self.speaking_model = None
            self.writing_model = None

    def _ensure_client(self) -> None:
        if not self.enabled:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        if self.client is not None and self._types is not None:
            return

        try:
            # Lazy import prevents Django startup/migrations from importing heavy
            # SDK modules during URL/check loading.
            from google import genai
            from google.genai import types
        except ModuleNotFoundError as exc:
            pkg = getattr(exc, "name", "unknown")
            raise RuntimeError(
                f"Missing Python dependency '{pkg}'. Install backend requirements and restart the server."
            ) from exc

        self.client = genai.Client(api_key=self.api_key)
        self._types = types

    def _generate_json(self, prompt: str, task: str) -> dict[str, Any]:
        model = self.writing_model if task == "writing" else self.speaking_model
        if not model:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        self._ensure_client()

        retry_count = max(1, int(os.getenv("GEMINI_JSON_RETRY_COUNT", "2")))
        attempt_prompt = prompt
        last_error: Exception | None = None

        for _ in range(retry_count):
            response = self.client.models.generate_content(
                model=model,
                contents=attempt_prompt,
                config=self._types.GenerateContentConfig(
                    temperature=self.generation_config["temperature"],
                    top_p=self.generation_config["top_p"],
                    candidate_count=self.generation_config["candidate_count"],
                    response_mime_type="application/json",
                ),
            )
            text = getattr(response, "text", None) or str(response)
            try:
                return extract_json_from_text(text)
            except Exception as exc:
                last_error = exc
                attempt_prompt = (
                    f"{prompt}\n\n"
                    "Your previous response was not valid JSON for the required schema. "
                    "Return one valid JSON object only. No markdown. No explanations."
                )

        raise ValueError("Model output did not contain a valid JSON object") from last_error

    def _generate_json_multimodal(self, text_prompt: str, image_bytes: bytes, image_mime_type: str | None) -> dict[str, Any]:
        if not self.writing_model:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        self._ensure_client()

        mime_type = image_mime_type if image_mime_type in {"image/jpeg", "image/png"} else "image/png"

        retry_count = max(1, int(os.getenv("GEMINI_JSON_RETRY_COUNT", "2")))
        attempt_prompt = text_prompt
        last_error: Exception | None = None

        for _ in range(retry_count):
            response = self.client.models.generate_content(
                model=self.writing_model,
                contents=[
                    attempt_prompt,
                    self._types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                ],
                config=self._types.GenerateContentConfig(
                    temperature=self.generation_config["temperature"],
                    top_p=self.generation_config["top_p"],
                    candidate_count=self.generation_config["candidate_count"],
                    response_mime_type="application/json",
                ),
            )
            text = getattr(response, "text", None) or str(response)
            try:
                return extract_json_from_text(text)
            except Exception as exc:
                last_error = exc
                attempt_prompt = (
                    f"{text_prompt}\n\n"
                    "Your previous response was not valid JSON for the required schema. "
                    "Return one valid JSON object only. No markdown. No explanations."
                )

        raise ValueError("Model output did not contain a valid JSON object") from last_error

    @staticmethod
    def _to_score(value: Any, label: str) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid '{label}' score value: {value!r}") from exc

        if score < 0 or score > 9:
            raise ValueError(f"Out-of-range '{label}' score: {score}")
        return score

    @staticmethod
    def _normalize_criteria_feedback(raw: Any, criteria_key: str) -> dict[str, list[dict[str, str]]]:
        allowed = [criteria_key, "cc", "lr", "gra"]
        normalized: dict[str, list[dict[str, str]]] = {key: [] for key in allowed}
        if not isinstance(raw, dict):
            return normalized

        for key in allowed:
            issues = raw.get(key, [])
            if not isinstance(issues, list):
                continue
            cleaned: list[dict[str, str]] = []
            for item in issues[:300]:
                if not isinstance(item, dict):
                    continue
                issue = str(item.get("issue", "")).strip()
                suggestion = str(item.get("suggestion", "")).strip()
                excerpt = str(item.get("excerpt", "")).strip()
                if issue or suggestion or excerpt:
                    cleaned.append(
                        {
                            "issue": issue,
                            "suggestion": suggestion,
                            "excerpt": excerpt,
                        }
                    )
            normalized[key] = cleaned
        return normalized

    @staticmethod
    def _normalize_inline_suggestions(raw: Any) -> list[dict[str, str]]:
        if not isinstance(raw, list):
            return []
        out: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for item in raw[:300]:
            if not isinstance(item, dict):
                continue
            span_text = str(item.get("span_text", "")).strip()
            issue = str(item.get("issue", "")).strip()
            suggestion = str(item.get("suggestion", "")).strip()
            criterion = str(item.get("criterion", "")).strip().lower()
            if span_text and (issue or suggestion):
                key = (span_text.lower(), suggestion.lower())
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "span_text": span_text,
                        "issue": issue,
                        "suggestion": suggestion,
                        "criterion": criterion,
                    }
                )
        return out

    @staticmethod
    def _dedupe_criteria_feedback(
        feedback: dict[str, list[dict[str, str]]],
        criteria_key: str,
    ) -> dict[str, list[dict[str, str]]]:
        allowed = [criteria_key, "cc", "lr", "gra"]
        deduped: dict[str, list[dict[str, str]]] = {key: [] for key in allowed}
        for key in allowed:
            seen: set[tuple[str, str]] = set()
            for item in feedback.get(key, []):
                excerpt = str(item.get("excerpt", "")).strip()
                suggestion = str(item.get("suggestion", "")).strip()
                issue = str(item.get("issue", "")).strip()
                # Merge near-duplicates that point to the same text and same fix.
                dedupe_key = (excerpt.lower(), suggestion.lower())
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                deduped[key].append(
                    {
                        "issue": issue,
                        "suggestion": suggestion,
                        "excerpt": excerpt,
                    }
                )
            # Keep all deduped issues for this criterion; no hard cap here.
            deduped[key] = deduped[key]
        return deduped

    @staticmethod
    def _normalize_corrections(raw: Any) -> list[dict[str, str]]:
        if not isinstance(raw, list):
            return []

        out: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for item in raw[:300]:
            if not isinstance(item, dict):
                continue
            error = str(item.get("error", "")).strip()
            correction = str(item.get("correction", "")).strip()
            if not error and not correction:
                continue
            key = (error.lower(), correction.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append({"error": error, "correction": correction})
        return out

    @staticmethod
    def _augment_corrections(
        corrections: list[dict[str, str]],
        criteria_feedback: dict[str, list[dict[str, str]]],
        inline_suggestions: list[dict[str, str]],
        minimum: int = 20,
    ) -> list[dict[str, str]]:
        if len(corrections) >= minimum:
            return corrections

        seen: set[tuple[str, str]] = {
            (str(item.get("error", "")).strip().lower(), str(item.get("correction", "")).strip().lower())
            for item in corrections
        }
        merged = list(corrections)

        for issues in criteria_feedback.values():
            for item in issues:
                error = str(item.get("excerpt", "")).strip() or str(item.get("issue", "")).strip()
                correction = str(item.get("suggestion", "")).strip()
                if not error or not correction:
                    continue
                key = (error.lower(), correction.lower())
                if key in seen:
                    continue
                seen.add(key)
                merged.append({"error": error, "correction": correction})
                if len(merged) >= minimum:
                    return merged

        for item in inline_suggestions:
            error = str(item.get("span_text", "")).strip() or str(item.get("issue", "")).strip()
            correction = str(item.get("suggestion", "")).strip()
            if not error or not correction:
                continue
            key = (error.lower(), correction.lower())
            if key in seen:
                continue
            seen.add(key)
            merged.append({"error": error, "correction": correction})
            if len(merged) >= minimum:
                return merged

        return merged

    @staticmethod
    def _merge_unique_corrections(*groups: list[dict[str, str]]) -> list[dict[str, str]]:
        merged: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for group in groups:
            for item in group:
                error = str(item.get("error", "")).strip()
                correction = str(item.get("correction", "")).strip()
                if not error and not correction:
                    continue
                key = (error.lower(), correction.lower())
                if key in seen:
                    continue
                seen.add(key)
                merged.append({"error": error, "correction": correction})
        return merged

    @staticmethod
    def _merge_unique_inline_suggestions(*groups: list[dict[str, str]]) -> list[dict[str, str]]:
        merged: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for group in groups:
            for item in group:
                span_text = str(item.get("span_text", "")).strip()
                issue = str(item.get("issue", "")).strip()
                suggestion = str(item.get("suggestion", "")).strip()
                criterion = str(item.get("criterion", "")).strip().lower()
                if not span_text or not (issue or suggestion):
                    continue
                key = (span_text.lower(), issue.lower(), suggestion.lower())
                if key in seen:
                    continue
                seen.add(key)
                merged.append(
                    {
                        "span_text": span_text,
                        "issue": issue,
                        "suggestion": suggestion,
                        "criterion": criterion,
                    }
                )
        return merged

    def _proofread_writing_exhaustive(self, task_type: str, essay: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        if not self.writing_model:
            return ([], [])

        proofread_prompt = f"""
You are a strict English proofreader for IELTS writing.
Find grammar, agreement, article, preposition, tense, punctuation, capitalization, and collocation errors.
This pass is exhaustive: capture as many real issues as possible.
Return strict JSON only.

Expected JSON schema:
{{
  "corrections": [{{"error": "exact phrase from essay", "correction": "fixed phrase"}}],
  "inline_suggestions": [
    {{"span_text": "exact phrase from essay", "issue": "short issue label", "suggestion": "fixed wording", "criterion": "gra|lr|cc|tr|ta"}}
  ]
}}

Hard rules:
- Include all real, non-duplicate corrections you can find (at least 12 when available).
- `error` and `span_text` must be exact text copied from the essay.
- Explicitly check subject-verb agreement across the full essay.
- Do not include duplicates.
- Do not produce multiple items for the same excerpt with the same correction.

Task type: {task_type}
Essay:
{essay}
"""
        try:
            parsed = self._generate_json(proofread_prompt, task="writing")
        except Exception:
            return ([], [])
        return (
            self._normalize_corrections(parsed.get("corrections")),
            self._normalize_inline_suggestions(parsed.get("inline_suggestions")),
        )

    def evaluate_writing(
        self,
        task_type: str,
        prompt: str,
        essay: str,
        topic_image_url: str | None = None,
        topic_image_bytes: bytes | None = None,
        topic_image_mime_type: str | None = None,
    ) -> dict[str, Any]:
        word_count = len([w for w in essay.split() if w.strip()])
        task_type = (task_type or "task2").lower()
        criteria_key = "ta" if task_type == "task1" else "tr"

        system_prompt = IELTS_TASK_1_EXAMINER_PROMPT if task_type == "task1" else IELTS_TASK_2_EXAMINER_PROMPT

        if not self.writing_model:
            c1 = 6.0 if word_count >= (150 if task_type == "task1" else 250) else 5.0
            c2, c3, c4 = 6.0, 6.0, 6.0
            overall = average_score([c1, c2, c3, c4])
            return {
                "task_type": task_type,
                "scores": {criteria_key: c1, "cc": c2, "lr": c3, "gra": c4, "overall_band": overall},
                "examiner_comments": "Fallback result generated because GEMINI_API_KEY is missing.",
                "corrections": [],
                "criteria_feedback": {criteria_key: [], "cc": [], "lr": [], "gra": []},
                "inline_suggestions": [],
                "word_count": word_count,
                "topic_image_url": topic_image_url,
            }

        user_prompt = f"""
{system_prompt}

Evaluate this IELTS essay and return strict JSON only.

Expected JSON schema:
{{
  "scores": {{"{criteria_key}": number, "cc": number, "lr": number, "gra": number, "overall_band": number}},
  "examiner_comments": "string",
  "corrections": [{{"error": "string", "correction": "string"}}],
  "criteria_feedback": {{
    "{criteria_key}": [{{"issue": "string", "suggestion": "string", "excerpt": "exact essay quote"}}],
    "cc": [{{"issue": "string", "suggestion": "string", "excerpt": "exact essay quote"}}],
    "lr": [{{"issue": "string", "suggestion": "string", "excerpt": "exact essay quote"}}],
    "gra": [{{"issue": "string", "suggestion": "string", "excerpt": "exact essay quote"}}]
  }},
  "inline_suggestions": [
    {{"span_text": "exact essay quote", "issue": "string", "suggestion": "improved wording", "criterion": "{criteria_key}|cc|lr|gra"}}
  ]
}}

Constraints:
- `examiner_comments` must be concise, direct, and under 80 words.
- Return rich, specific feedback, not a single issue.
- `corrections` must include all concrete language errors found in the essay (grammar, wording, punctuation, agreement, article/preposition, tense, capitalization), with at least 12 when available.
- For `criteria_feedback`, provide all high-value issues for each criterion key (`{criteria_key}`, `cc`, `lr`, `gra`) when available, each with an exact excerpt from the essay.
- `inline_suggestions` should include all high-value span-level suggestions found, with exact `span_text` copied from the essay.
- Be exhaustive for language mistakes and avoid limiting output to just a few examples.
- Avoid overlap spam: do not output several differently named issues for the exact same excerpt and same suggested fix.
- Do not use vague placeholders such as "improve grammar"; each item must be actionable and tied to exact essay text.

Task type: {task_type}
Prompt: {prompt}
Topic image URL: {topic_image_url or ''}
Image note: If an image is provided, use it when judging whether the response is on-topic and accurate.
Essay:\n{essay}
"""
        parsed = (
            self._generate_json_multimodal(user_prompt, topic_image_bytes, topic_image_mime_type)
            if topic_image_bytes
            else self._generate_json(user_prompt, task="writing")
        )
        parsed["criteria_feedback"] = self._normalize_criteria_feedback(parsed.get("criteria_feedback"), criteria_key)
        parsed["criteria_feedback"] = self._dedupe_criteria_feedback(parsed["criteria_feedback"], criteria_key)
        parsed["inline_suggestions"] = self._normalize_inline_suggestions(parsed.get("inline_suggestions"))
        parsed["corrections"] = self._normalize_corrections(parsed.get("corrections"))

        proofreading_corrections, proofreading_inline = self._proofread_writing_exhaustive(task_type, essay)
        parsed["corrections"] = self._merge_unique_corrections(
            parsed["corrections"],
            proofreading_corrections,
        )
        parsed["inline_suggestions"] = self._merge_unique_inline_suggestions(
            parsed["inline_suggestions"],
            proofreading_inline,
        )
        parsed["corrections"] = self._augment_corrections(
            parsed["corrections"],
            parsed["criteria_feedback"],
            parsed["inline_suggestions"],
            minimum=12,
        )
        parsed["word_count"] = word_count
        parsed["task_type"] = task_type
        parsed["topic_image_url"] = topic_image_url
        return parsed

    def generate_speaking_turn_rewrite(self, examiner_question: str, candidate_response: str, target_band: int) -> dict[str, Any]:
        if target_band not in {7, 8, 9}:
            raise ValueError("target_band must be 7, 8, or 9")

        if not self.speaking_model:
            return {
                "rewritten_response": candidate_response,
                "improvements": [],
                "coach_summary": "Fallback rewrite because Gemini is not configured.",
            }

        user_prompt = f"""
You are an IELTS speaking coach.
Rewrite the candidate's response to the examiner's question so it can realistically score Band {target_band}.0.

Rules:
- Sound natural and conversational, appropriate for spoken English (not an academic essay).
- Keep the same core ideas and context.
- Improve vocabulary (idioms, less common items), grammar, and fluency/cohesion features.
- Return strict JSON only.

Expected JSON schema:
{{
  "rewritten_response": "string (the complete improved answer)",
  "coach_summary": "string (max 24 words explaining the overall upgrade)",
  "improvements": [
    {{
      "original_text": "exact short phrase from original response",
      "enhanced_text": "matching phrase in rewritten response",
      "why_better": "short reason, max 20 words",
      "criterion": "FC|LR|GRA"
    }}
  ]
}}

Constraints:
- Keep the rewrite close to the student's core meaning.
- Add 3-5 improvements only.
- `enhanced_text` must appear verbatim in `rewritten_response`.
- `original_text` must appear verbatim in original response.
- Keep reasons sharp and practical.

Examiner's Question: {examiner_question}
Candidate's Original Response: {candidate_response}
"""
        parsed = self._generate_json(user_prompt, task="speaking")
        rewritten = str(parsed.get("rewritten_response", "")).strip() or candidate_response
        improvements_raw = parsed.get("improvements", [])
        improvements: list[dict[str, str]] = []
        if isinstance(improvements_raw, list):
            for item in improvements_raw[:12]:
                if not isinstance(item, dict):
                    continue
                original_text = str(item.get("original_text", "")).strip()
                enhanced_text = str(item.get("enhanced_text", "")).strip()
                why_better = str(item.get("why_better", "")).strip()
                criterion = str(item.get("criterion", "")).strip().lower()
                if enhanced_text and why_better:
                    improvements.append(
                        {
                            "original_text": original_text,
                            "enhanced_text": enhanced_text,
                            "why_better": why_better,
                            "criterion": criterion,
                        }
                    )
        return {
            "rewritten_response": rewritten,
            "coach_summary": str(parsed.get("coach_summary", "")).strip(),
            "improvements": improvements,
        }

    def generate_band_rewrite(self, task_type: str, prompt: str, essay: str, target_band: int) -> dict[str, Any]:
        if target_band not in {7, 8, 9}:
            raise ValueError("target_band must be 7, 8, or 9")

        if not self.writing_model:
            return {
                "rewritten_essay": essay,
                "improvements": [],
                "coach_summary": "Fallback rewrite because Gemini is not configured.",
            }

        criteria_key = "TA" if task_type == "task1" else "TR"
        user_prompt = f"""
You are an IELTS writing coach.
Rewrite the essay so it can realistically score Band {target_band}.0.

Rules:
- Keep the same topic and context.
- Do not add new core ideas outside the student's original scope.
- Improve clarity, grammar, vocabulary, cohesion, and development only within the same argument/data context.
- Return strict JSON only.

Expected JSON schema:
{{
  "rewritten_essay": "string",
  "coach_summary": "string (max 24 words)",
  "improvements": [
    {{
      "original_text": "exact short phrase from original essay",
      "enhanced_text": "matching phrase in rewritten essay",
      "why_better": "short reason, max 20 words",
      "criterion": "{criteria_key}|CC|LR|GRA"
    }}
  ]
}}

Constraints:
- Keep the rewrite close to the student's core meaning. No major new ideas.
- Add 4-8 improvements only.
- `enhanced_text` must appear verbatim in `rewritten_essay`.
- `original_text` must appear verbatim in original essay.
- Keep reasons sharp and practical.

Task type: {task_type}
Primary criterion: {criteria_key}
Prompt: {prompt}
Original essay:
{essay}
"""
        parsed = self._generate_json(user_prompt, task="writing")
        rewritten = str(parsed.get("rewritten_essay", "")).strip() or essay
        improvements_raw = parsed.get("improvements", [])
        improvements: list[dict[str, str]] = []
        if isinstance(improvements_raw, list):
            for item in improvements_raw[:12]:
                if not isinstance(item, dict):
                    continue
                original_text = str(item.get("original_text", "")).strip()
                enhanced_text = str(item.get("enhanced_text", "")).strip()
                why_better = str(item.get("why_better", "")).strip()
                criterion = str(item.get("criterion", "")).strip().lower()
                if enhanced_text and why_better:
                    improvements.append(
                        {
                            "original_text": original_text,
                            "enhanced_text": enhanced_text,
                            "why_better": why_better,
                            "criterion": criterion,
                        }
                    )
        return {
            "rewritten_essay": rewritten,
            "coach_summary": str(parsed.get("coach_summary", "")).strip(),
            "improvements": improvements,
        }

    def _get_speaking_prompt(self, part: str) -> str:
        if part == "1":
            return IELTS_EXAMINER_PROMPT_PART1
        elif part == "2":
            return IELTS_EXAMINER_PROMPT_PART2
        elif part == "3":
            return IELTS_EXAMINER_PROMPT_PART3
        return IELTS_EXAMINER_PROMPT

    def generate_speaking_turn(self, conversation_history: list[dict[str, str]], part: str = "all") -> dict[str, Any]:
        if not self.speaking_model:
            return {"examiner_text": "Can you tell me more about that?", "part": "ongoing"}

        system_prompt = self._get_speaking_prompt(part)
        formatted_history = "\n".join([f"{item['role']}: {item['content']}" for item in conversation_history])
        prompt = f"""
{system_prompt}

Continue the IELTS speaking interview. Return strict JSON only:
{{"examiner_text": "...", "part": "1|2|3|ongoing|finished"}}

Conversation:
{formatted_history}
"""
        try:
            parsed = self._generate_json(prompt, task="speaking")
            # If the LLM intentionally returned an empty string, we keep it as empty.
            examiner_text = parsed.get("examiner_text", "")
            if examiner_text is None:
                examiner_text = ""
            examiner_text = str(examiner_text).strip()
            
            part = str(parsed.get("part", "ongoing")).strip().lower()
            if part not in {"1", "2", "3", "ongoing", "finished"}:
                part = "ongoing"
            
            return {"examiner_text": examiner_text, "part": part}
        except Exception:
            # Never break the speaking socket because of LLM formatting noise.
            return {"examiner_text": "Can you tell me more about that?", "part": "ongoing"}

    def generate_speaking_turn_stream(self, conversation_history: list[dict[str, str]], part: str = "all", forced_question: str = None):
        if not self.speaking_model:
            yield {"text": "Can you tell me more about that?", "is_last": True}
            return

        self._ensure_client()
        system_prompt = self._get_speaking_prompt(part)
        
        # Inject the latency optimization constraint
        system_prompt += "\n\nIMPORTANT: Always begin your response with a single short sentence of 8 words or fewer. This should be a direct acknowledgment or conversational opener. Then continue with your full response."
        
        if forced_question:
            system_prompt += f"\n\nCRITICAL INSTRUCTION FOR THIS TURN:\n{forced_question}"
            
        formatted_history = "\n".join([f"{item['role']}: {item['content']}" for item in conversation_history])
        
        # We don't ask for JSON in streaming because parsing incomplete JSON is complex.
        # We just ask for the direct text response. We can assume part="ongoing".
        # If the user wants part progression, we can either do a separate check or rely on explicit ending phrases.
        prompt = f"""
{system_prompt}

Continue the IELTS speaking interview. You must return ONLY the plain text of your spoken response as the examiner. 
Do NOT output JSON. Do NOT output a dict. Do NOT include markdown. 
Do NOT write "examiner_text". Do NOT include "part".
Just output the actual words you are saying right now, nothing else.

Conversation:
{formatted_history}
"""
        response_stream = self.client.models.generate_content_stream(
            model=self.speaking_model,
            contents=prompt,
            config=self._types.GenerateContentConfig(
                temperature=self.generation_config["temperature"],
                top_p=self.generation_config["top_p"],
                candidate_count=self.generation_config["candidate_count"],
            ),
        )

        for chunk in response_stream:
            if chunk.text:
                yield {"text": chunk.text, "is_last": False}
        
        yield {"text": "", "is_last": True}

    def generate_speaking_final_report(self, conversation_history: list[dict[str, str]], part: str = "all") -> dict[str, Any]:
        if not self.speaking_model:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        system_prompt = self._get_speaking_prompt(part)
        formatted_history = "\n".join([f"{item['role']}: {item['content']}" for item in conversation_history])
        prompt = f"""
{system_prompt}

The speaking test is complete. Return strict JSON only with this schema:
{{
  "scores": {{"fc": number, "lr": number, "gra": number, "overall_band": number}},
  "examiner_comments": "string",
  "corrections": [{{"error": "string", "correction": "string"}}],
  "criteria_feedback": {{
    "fc": [{{"issue": "string", "excerpt": "string", "suggestion": "string"}}],
    "lr": [{{"issue": "string", "excerpt": "string", "suggestion": "string"}}],
    "gra": [{{"issue": "string", "excerpt": "string", "suggestion": "string"}}]
  }},
  "inline_suggestions": [{{"span_text": "string", "issue": "string", "suggestion": "string", "criterion": "string"}}]
}}

IMPORTANT RULES FOR FEEDBACK:
- `examiner_comments` must be concise, direct, and under 80 words.
- `corrections` must include concrete language errors found in the candidate's speech.
- `criteria_feedback` must provide high-value issues for each criterion (fc, lr, gra) with an exact `excerpt` copied from the candidate's speech.
- `inline_suggestions` must include specific span-level suggestions with exact `span_text` copied from the candidate's speech.
- Only extract excerpts from the candidate's ("user") turns, not the examiner's ("assistant") turns.

Conversation:
{formatted_history}
"""
        parsed = self._generate_json(prompt, task="speaking")
        if not isinstance(parsed, dict):
            raise ValueError("Speaking report response is not a JSON object")

        scores = parsed.get("scores")
        if not isinstance(scores, dict):
            raise ValueError("Missing or invalid 'scores' object in speaking report")

        fc = self._to_score(scores.get("fc"), "fc")
        lr = self._to_score(scores.get("lr"), "lr")
        gra = self._to_score(scores.get("gra"), "gra")
        overall = self._to_score(scores.get("overall_band", average_score([fc, lr, gra])), "overall_band")

        comments = parsed.get("examiner_comments", "")
        if not isinstance(comments, str) or not comments.strip():
            comments = "No detailed comments provided."

        criteria_feedback = parsed.get("criteria_feedback", {})
        # Normalize and deduplicate similar to writing
        normalized_criteria = {}
        for key in ["fc", "lr", "gra"]:
            normalized_criteria[key] = criteria_feedback.get(key, [])
        
        parsed["criteria_feedback"] = self._dedupe_criteria_feedback(normalized_criteria, "fc")
        parsed["inline_suggestions"] = self._normalize_inline_suggestions(parsed.get("inline_suggestions"))
        parsed["corrections"] = self._normalize_corrections(parsed.get("corrections"))
        parsed["corrections"] = self._augment_corrections(
            parsed["corrections"],
            parsed["criteria_feedback"],
            parsed["inline_suggestions"],
            minimum=5,
        )

        return {
            "scores": {"fc": fc, "lr": lr, "gra": gra, "overall_band": overall},
            "examiner_comments": comments.strip(),
            "criteria_feedback": parsed["criteria_feedback"],
            "inline_suggestions": parsed["inline_suggestions"],
            "corrections": parsed["corrections"]
        }

    def generate_speaking_quick_scores(self, conversation_history: list[dict[str, str]], part: str = "all") -> dict[str, float]:
        if not self.speaking_model:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        system_prompt = self._get_speaking_prompt(part)
        formatted_history = "\n".join([f"{item['role']}: {item['content']}" for item in conversation_history])
        prompt = f"""
{system_prompt}

The speaking test is complete. Return strict JSON only with this schema:
{{
  "scores": {{"fc": number, "lr": number, "gra": number, "overall_band": number}}
}}

Provide best-estimate scores quickly using the full conversation.

Conversation:
{formatted_history}
"""
        parsed = self._generate_json(prompt, task="speaking")
        if not isinstance(parsed, dict):
            raise ValueError("Quick speaking score response is not a JSON object")

        scores = parsed.get("scores")
        if not isinstance(scores, dict):
            raise ValueError("Missing or invalid 'scores' object in quick speaking score response")

        fc = self._to_score(scores.get("fc"), "fc")
        lr = self._to_score(scores.get("lr"), "lr")
        gra = self._to_score(scores.get("gra"), "gra")
        overall = self._to_score(scores.get("overall_band", average_score([fc, lr, gra])), "overall_band")
        return {"fc": fc, "lr": lr, "gra": gra, "overall_band": overall}
