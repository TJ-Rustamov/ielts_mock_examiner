import json
import re
from typing import Any


def extract_json_from_text(text: str) -> dict[str, Any]:
    """Extract a JSON object from model output that may include wrappers/noise."""
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Model output was empty")

    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, flags=re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(cleaned[index:])
            if isinstance(candidate, dict):
                return candidate
        except json.JSONDecodeError:
            continue

    raise ValueError("Model output did not contain a valid JSON object")


def average_score(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 1)
