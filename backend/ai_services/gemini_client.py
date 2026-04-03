import os
from typing import Any

from ai_services.prompts import (
    IELTS_EXAMINER_PROMPT,
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
  "corrections": [{{"error": "string", "correction": "string"}}]
}}

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
        parsed["word_count"] = word_count
        parsed["task_type"] = task_type
        parsed["topic_image_url"] = topic_image_url
        return parsed

    def generate_speaking_turn(self, conversation_history: list[dict[str, str]]) -> dict[str, Any]:
        if not self.speaking_model:
            return {"examiner_text": "Can you tell me more about that?", "part": "ongoing"}

        formatted_history = "\n".join([f"{item['role']}: {item['content']}" for item in conversation_history])
        prompt = f"""
{IELTS_EXAMINER_PROMPT}

Continue the IELTS speaking interview. Return strict JSON only:
{{"examiner_text": "...", "part": "1|2|3|ongoing|finished"}}

Conversation:
{formatted_history}
"""
        try:
            parsed = self._generate_json(prompt, task="speaking")
            examiner_text = str(parsed.get("examiner_text", "")).strip()
            part = str(parsed.get("part", "ongoing")).strip().lower()
            if part not in {"1", "2", "3", "ongoing", "finished"}:
                part = "ongoing"
            if not examiner_text:
                examiner_text = "Can you tell me more about that?"
            return {"examiner_text": examiner_text, "part": part}
        except Exception:
            # Never break the speaking socket because of LLM formatting noise.
            return {"examiner_text": "Can you tell me more about that?", "part": "ongoing"}

    def generate_speaking_final_report(self, conversation_history: list[dict[str, str]]) -> dict[str, Any]:
        if not self.speaking_model:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        formatted_history = "\n".join([f"{item['role']}: {item['content']}" for item in conversation_history])
        prompt = f"""
{IELTS_EXAMINER_PROMPT}

The speaking test is complete. Return strict JSON only with this schema:
{{
  "scores": {{"fc": number, "lr": number, "gra": number, "overall_band": number}},
  "analysis": {{
    "fc": {{"good": ["..."], "not_so_good": ["..."]}},
    "lr": {{"good": ["..."], "not_so_good": ["..."]}},
    "gra": {{"good": ["..."], "not_so_good": ["..."]}}
  }},
  "examiner_comments": "string"
}}

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

        analysis = parsed.get("analysis")
        if not isinstance(analysis, dict):
            raise ValueError("Missing or invalid 'analysis' object in speaking report")

        comments = parsed.get("examiner_comments")
        if not isinstance(comments, str) or not comments.strip():
            raise ValueError("Missing or invalid 'examiner_comments' in speaking report")

        return {
            "scores": {"fc": fc, "lr": lr, "gra": gra, "overall_band": overall},
            "analysis": analysis,
            "examiner_comments": comments.strip(),
        }
