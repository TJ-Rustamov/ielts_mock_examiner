"""Answer-sheet review: self-check verdicts, blind reveal, crops, corrections.

The Django side of :mod:`exams.keycheck`. That module decides whether each
answer can be trusted from plain dicts; this one feeds it rows from the
database and keeps ``AnswerKeySheet.evidence`` current as the sheet changes.

The point of all of it is that someone who is going to sit a test can confirm
its key without reading it: the self-checks vouch for most answers, and the
few they cannot vouch for are revealed one at a time, next to a crop of the
book's own key row so the check is against the printed page, not memory.
"""

from __future__ import annotations

import io
import os

from django.utils import timezone

from exams import keycheck
from exams.importer import boilerplate as bp
from exams.models import AnswerKeySheet, ImportJob, Module, QuestionGroup

__all__ = [
    "groups_for",
    "lexicons_for",
    "recheck",
    "masked_cells",
    "reveal",
    "confirm",
    "record_edits",
    "blind_blockers",
    "source_pdf_for",
    "render_crop",
    "correct_after_attempt",
]


def groups_for(module: Module) -> list[keycheck.GroupInfo]:
    """GroupInfo from the published groups of a module."""
    from exams.importer.classify import _extract_letter_range

    groups = []
    rows = QuestionGroup.objects.filter(section__module=module).select_related("section")
    for group in rows:
        groups.append(keycheck.GroupInfo(
            type=group.type or bp.UNKNOWN,
            first=group.first_question,
            last=group.last_question,
            options=[o.get("letter") for o in (group.options or [])
                     if isinstance(o, dict) and o.get("letter")],
            # Not stored on the row; the rubric still says it.
            letter_range=_extract_letter_range(group.instruction_text or ""),
            word_limit=group.word_limit or "",
            select_count=group.select_count,
            section=group.section.order,
        ))
    return groups


def lexicons_for(module: Module) -> dict[int, str]:
    """Section order -> passage text (Reading) or audioscript (Listening)."""
    out: dict[int, str] = {}
    for section in module.sections.all():
        text = section.passage_html or section.transcript_text or ""
        if text:
            out[section.order] = text
    return out


def recheck(sheet: AnswerKeySheet, save: bool = True) -> dict[int, keycheck.CellReport]:
    """Re-run the self-checks over the sheet's current answers."""
    module = sheet.module
    total = module.total_questions or 40
    evidence = {k: dict(v) for k, v in (sheet.evidence or {}).items() if isinstance(v, dict)}
    reports = keycheck.check_module(
        groups_for(module), sheet.answers or {}, evidence, lexicons_for(module), total=total,
    )
    for number, report in reports.items():
        entry = evidence.setdefault(str(number), {})
        entry["check"] = report.to_json()
    sheet.evidence = evidence
    if save:
        sheet.save(update_fields=["evidence", "updated_at"])
    return reports


def masked_cells(sheet: AnswerKeySheet) -> dict[str, dict]:
    """Per-question status for the blind screen - and nothing that gives the answer away.

    The check notes are left out too: "corrected to the passage spelling" or
    "the readings disagree ('cafe' ...)" would leak the answer.
    """
    total = sheet.module.total_questions or 40
    revealed = set(sheet.revealed or [])
    cells: dict[str, dict] = {}
    for number in range(1, total + 1):
        value = sheet.answers.get(str(number)) or {}
        entry = (sheet.evidence or {}).get(str(number)) or {}
        check = entry.get("check") or {}
        cells[str(number)] = {
            "status": sheet.cell_status(number),
            "kind": value.get("kind") or "",
            "set_numbers": value.get("set_numbers") or [],
            "checks": [
                {"name": c.get("name"), "result": c.get("result")}
                for c in check.get("checks") or []
            ],
            "source": entry.get("source") or "",
            "has_crop": bool(entry.get("crop")),
            "revealed": number in revealed,
        }
    return cells


def reveal(sheet: AnswerKeySheet, number: int) -> dict:
    """One question's answer and everything known about it. Recorded."""
    revealed = list(sheet.revealed or [])
    if number not in revealed:
        revealed.append(number)
        sheet.revealed = sorted(revealed)
        sheet.save(update_fields=["revealed", "updated_at"])
    entry = dict((sheet.evidence or {}).get(str(number)) or {})
    return {
        "number": number,
        "status": sheet.cell_status(number),
        "answer": sheet.answers.get(str(number)),
        "proposed": (sheet.proposed_answers or {}).get(str(number)),
        "raw_text": (sheet.raw_text or {}).get(str(number), ""),
        "evidence": {k: v for k, v in entry.items() if k not in ("check", "history")},
        "check": entry.get("check") or {},
        "history": entry.get("history") or [],
        "has_crop": bool(entry.get("crop")),
    }


def confirm(sheet: AnswerKeySheet, numbers) -> list[int]:
    """Mark answers as looked at and accepted by a person."""
    total = sheet.module.total_questions or 40
    confirmed = set(sheet.confirmed or [])
    added = []
    for raw in numbers or []:
        try:
            number = int(raw)
        except (TypeError, ValueError):
            continue
        if 1 <= number <= total and str(number) in (sheet.answers or {}):
            confirmed.add(number)
            added.append(number)
    sheet.confirmed = sorted(confirmed)
    return added


def record_edits(sheet: AnswerKeySheet, before: dict, user=None) -> list[int]:
    """Note which cells a person changed; a changed cell counts as confirmed.

    Typing an answer in means someone looked at it, so it no longer needs the
    self-checks to vouch for it - but they still run, and a structural failure
    (a letter the options do not offer) still shows.
    """
    changed = []
    evidence = dict(sheet.evidence or {})
    stamp = timezone.now().isoformat()
    for number, value in (sheet.answers or {}).items():
        if before.get(number) != value:
            changed.append(int(number))
            entry = dict(evidence.get(number) or {})
            history = list(entry.get("history") or [])
            history.append({
                "at": stamp,
                "by": getattr(user, "username", "") or "",
                "from": (before.get(number) or {}).get("accepted"),
                "to": value.get("accepted"),
            })
            entry["history"] = history[-10:]
            entry["source"] = "manual"
            evidence[number] = entry
    sheet.evidence = evidence
    if changed:
        sheet.confirmed = sorted(set(sheet.confirmed or []) | set(changed))
    return sorted(changed)


def blind_blockers(sheet: AnswerKeySheet) -> list[int]:
    """Questions that stop a blind verification: not trusted and not confirmed."""
    total = sheet.module.total_questions or 40
    return [
        number for number in range(1, total + 1)
        if sheet.cell_status(number) not in (keycheck.TRUSTED, keycheck.CONFIRMED)
    ]


# ---------------------------------------------------------------------------
# Crops
# ---------------------------------------------------------------------------


def source_pdf_for(module: Module) -> str:
    """Path of the book PDF a module was imported from, if it is still on disk."""
    jobs = ImportJob.objects.filter(book=module.test.book).exclude(source_file="")
    jobs = jobs.order_by("-created_at")
    for job in jobs:
        try:
            path = job.source_file.path
        except (ValueError, NotImplementedError):
            continue
        if path and os.path.exists(path):
            return path
    # A job published before it was linked to the book still carries the slug.
    for job in ImportJob.objects.filter(book_slug=module.test.book.slug).order_by("-created_at"):
        try:
            path = job.source_file.path
        except (ValueError, NotImplementedError):
            continue
        if path and os.path.exists(path):
            return path
    return ""


#: Breathing room around a key row, in PDF points.
CROP_PADDING = 10.0
CROP_DPI = 200


def render_crop(sheet: AnswerKeySheet, number: int) -> bytes | None:
    """PNG of the printed key row for one question, or None.

    Cut from the book PDF on demand rather than stored: forty small images per
    module would be clutter, and the PDF is the original anyway. Answers read
    from an uploaded photo are cut from that photo instead.
    """
    entry = (sheet.evidence or {}).get(str(number)) or {}
    crop = entry.get("crop")
    if not crop or not crop.get("bbox"):
        return None
    x0, y0, x1, y1 = (float(v) for v in crop["bbox"])
    # Pad generously sideways - the number sits left of the answer - and a
    # little vertically, so the neighbouring rows are visible for context.
    height = max(y1 - y0, 8.0)
    box = (x0 - CROP_PADDING * 2, y0 - height * 0.8, x1 + CROP_PADDING * 6, y1 + height * 0.8)

    if crop.get("image"):
        return _crop_image(sheet, box, crop)

    path = source_pdf_for(sheet.module)
    page_number = crop.get("page")
    if not path or not page_number:
        return None
    from exams.importer import pdfsource

    document = pdfsource.open_document(path)
    try:
        index = int(page_number) - 1
        if not 0 <= index < document.page_count:
            return None
        page = document[index]
        fitz = pdfsource._fitz()
        rect = fitz.Rect(*box) & page.rect
        if rect.is_empty:
            return None
        return pdfsource.render_clip(page, tuple(rect), dpi=CROP_DPI)
    finally:
        document.close()


def _crop_image(sheet: AnswerKeySheet, box, crop) -> bytes | None:
    if not sheet.image:
        return None
    from PIL import Image

    try:
        with sheet.image.open("rb") as handle:
            image = Image.open(io.BytesIO(handle.read()))
            image.load()
    except Exception:
        return None
    page_width = float(crop.get("page_width") or 0) or 595.0
    scale = image.size[0] / page_width
    left, top, right, bottom = (max(0, int(v * scale)) for v in box)
    right, bottom = min(image.size[0], right), min(image.size[1], bottom)
    if right - left < 2 or bottom - top < 2:
        return None
    buffer = io.BytesIO()
    image.crop((left, top, right, bottom)).save(buffer, format="PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# After an attempt
# ---------------------------------------------------------------------------


def correct_after_attempt(sheet: AnswerKeySheet, number: int, accepted: list[str], user=None):
    """Fix one answer on a verified key, from the results screen.

    The person has just sat the test and is looking at the book's key row for
    this question, so the sheet stays verified - unpublishing the module over a
    one-cell fix would hide it from everyone mid-week. The change is logged on
    the cell and attempts are re-marked by the caller.
    """
    from exams.keygrammar import detect_kind

    key = str(number)
    before = dict(sheet.answers or {})
    current = dict(before.get(key) or {})
    cleaned = [str(a).strip() for a in accepted if str(a).strip()]
    current["accepted"] = cleaned
    if not current.get("kind") or current.get("kind") == "text":
        current["kind"] = detect_kind(tuple(cleaned))
    answers = dict(before)
    answers[key] = current
    # Partners in an "IN EITHER ORDER" set share one answer.
    for partner in current.get("set_numbers") or []:
        if str(partner) != key and str(partner) in answers:
            answers[str(partner)] = dict(current)
    sheet.answers = answers
    record_edits(sheet, before, user)
    recheck(sheet, save=False)
    sheet.save(update_fields=["answers", "evidence", "confirmed", "updated_at"])
    return current
