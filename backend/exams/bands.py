"""Raw score (out of 40) to IELTS band conversion.

Pure module: no Django imports, so it is unit-testable without a database.

IMPORTANT — these tables are *indicative*. Cambridge varies the conversion
slightly from test to test and does not publish exact tables; the books only
give a coarse "if you score 0-19 / 20-28 / 29-40" sidebar. These are the
widely-circulated standard conversions. `Attempt.band_table_version` records
which table produced a stored band, so historical results stay auditable if
these ever change.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

# (min_raw, max_raw, band) — inclusive ranges, descending.
READING_ACADEMIC_V1: tuple[tuple[int, int, str], ...] = (
    (39, 40, "9.0"),
    (37, 38, "8.5"),
    (35, 36, "8.0"),
    (33, 34, "7.5"),
    (30, 32, "7.0"),
    (27, 29, "6.5"),
    (23, 26, "6.0"),
    (19, 22, "5.5"),
    (15, 18, "5.0"),
    (13, 14, "4.5"),
    (10, 12, "4.0"),
    (8, 9, "3.5"),
    (6, 7, "3.0"),
    (4, 5, "2.5"),
    (3, 3, "2.0"),
    (2, 2, "1.5"),
    (1, 1, "1.0"),
    (0, 0, "0.0"),
)

LISTENING_V1: tuple[tuple[int, int, str], ...] = (
    (39, 40, "9.0"),
    (37, 38, "8.5"),
    (35, 36, "8.0"),
    (32, 34, "7.5"),
    (30, 31, "7.0"),
    (26, 29, "6.5"),
    (23, 25, "6.0"),
    (18, 22, "5.5"),
    (16, 17, "5.0"),
    (13, 15, "4.5"),
    (11, 12, "4.0"),
    (8, 10, "3.5"),
    (6, 7, "3.0"),
    (4, 5, "2.5"),
    (3, 3, "2.0"),
    (2, 2, "1.5"),
    (1, 1, "1.0"),
    (0, 0, "0.0"),
)

# (kind, variant, version) -> table
_TABLES: dict[tuple[str, str, str], tuple[tuple[int, int, str], ...]] = {
    ("reading", "academic", "v1"): READING_ACADEMIC_V1,
    ("listening", "academic", "v1"): LISTENING_V1,
    # Listening uses one table for both variants.
    ("listening", "general", "v1"): LISTENING_V1,
}

CURRENT_VERSION = "v1"
MAX_RAW = 40


class UnknownBandTable(LookupError):
    """Raised when no conversion table is registered for a kind/variant/version."""


def get_table(
    kind: str,
    variant: str = "academic",
    version: str = CURRENT_VERSION,
) -> tuple[tuple[int, int, str], ...]:
    try:
        return _TABLES[(kind, variant, version)]
    except KeyError as exc:
        raise UnknownBandTable(
            f"No band table for kind={kind!r} variant={variant!r} version={version!r}"
        ) from exc


def raw_to_band(
    kind: str,
    raw: int,
    variant: str = "academic",
    version: str = CURRENT_VERSION,
) -> Decimal:
    """Convert a raw score to a band.

    `raw` is clamped to 0..40 rather than rejected: a prorated or partial-test
    score should still produce a band rather than blowing up mid-request.
    """
    table = get_table(kind, variant, version)
    score = max(0, min(int(raw), MAX_RAW))
    for low, high, band in table:
        if low <= score <= high:
            return Decimal(band)
    # Tables cover 0..40 exhaustively; this is unreachable unless one is edited badly.
    raise UnknownBandTable(f"Band table for {kind}/{variant}/{version} has no entry for raw={score}")


def round_ielts_half(value: float | Decimal) -> Decimal:
    """Round to the nearest half band, IELTS-style.

    A fractional part of .25 or more rounds up to .5; .75 or more rounds up to
    the next whole band. Note this is NOT ordinary rounding: 6.25 -> 6.5.
    """
    as_float = float(value)
    whole = int(as_float // 1)
    frac = as_float - whole
    if frac < 0.25:
        result = Decimal(whole)
    elif frac < 0.75:
        result = Decimal(whole) + Decimal("0.5")
    else:
        result = Decimal(whole + 1)
    return result.quantize(Decimal("0.1"))


def overall_band(bands: Iterable[float | Decimal | None]) -> Decimal | None:
    """Mean of the available skill bands, rounded to the nearest half band.

    Missing skills are skipped rather than counted as zero — a candidate who has
    only sat Reading should see their Reading band, not a meaningless average
    dragged down by three absent scores.
    """
    present = [float(b) for b in bands if b is not None]
    if not present:
        return None
    return round_ielts_half(sum(present) / len(present))


def prorate(raw: int, answered_questions: int, total: int = MAX_RAW) -> int:
    """Scale a raw score up to /40 when a test has fewer than 40 usable questions.

    Used when the importer had to exclude an unparseable group. The result is
    an estimate and callers must label it as such in the UI.
    """
    if answered_questions <= 0:
        return 0
    if answered_questions >= total:
        return max(0, min(int(raw), total))
    scaled = round(int(raw) * total / answered_questions)
    return max(0, min(scaled, total))
