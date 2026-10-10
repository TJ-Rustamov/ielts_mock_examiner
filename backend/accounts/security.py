"""Per-user test-security switches.

Every switch defaults to on, which is how the tests behaved before switches
existed, so a user who never opens Settings sees no change.
"""

from __future__ import annotations

#: key -> default. The frontend mirrors these in src/lib/security-settings.ts.
DEFAULTS: dict[str, bool] = {
    # Speaking: switching tab or window asks whether to cancel the test.
    "leave_window_cancels_speaking": True,
    # Reading/Listening: count leaving the window and show the count.
    "count_leaving_window": True,
    # Reading: block copying the passage text.
    "block_copying": True,
    # Any test: the browser asks before the page is closed or refreshed.
    "warn_before_leaving_page": True,
}


def effective(stored: dict | None) -> dict[str, bool]:
    """The full set of switches: stored choices over the defaults."""
    stored = stored if isinstance(stored, dict) else {}
    return {key: bool(stored.get(key, default)) for key, default in DEFAULTS.items()}


def clean(changes) -> tuple[dict[str, bool], list[str]]:
    """Validate a partial update. Unknown keys and non-boolean values are errors."""
    if not isinstance(changes, dict):
        return {}, ["expected an object of switches"]
    cleaned: dict[str, bool] = {}
    problems: list[str] = []
    for key, value in changes.items():
        if key not in DEFAULTS:
            problems.append(f"unknown setting {key!r}")
        elif not isinstance(value, bool):
            problems.append(f"{key!r} must be true or false")
        else:
            cleaned[key] = value
    return cleaned, problems
