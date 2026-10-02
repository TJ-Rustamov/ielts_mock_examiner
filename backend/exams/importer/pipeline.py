"""Orchestrator: PDF in, reviewable draft payload out.

Runs the stages in order and collects warnings rather than failing. A book that
parses badly must still produce a draft an admin can correct — the one outcome
that is never acceptable is a confident, wrong answer key.

No Django imports, so the whole pipeline can be exercised from a plain script.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from exams import keygrammar
from exams.importer import boilerplate as bp
from exams.importer import pdfsource
from exams.importer.classify import classify, normalise_instruction
from exams.importer.layout import read_page, strip_repeated_chrome
from exams.importer.parsers import ParsedGroup, parse_group
from exams.importer.passages import passage_regions
from exams.importer.segment import (
    LISTENING,
    READING,
    Document,
    is_structural_anchor,
    segment,
)

__all__ = ["ImportResult", "run", "content_hash"]

PARSER_VERSION = "1.0.0"


@dataclass
class ImportResult:
    book: dict = field(default_factory=dict)
    tests: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unmatched_instructions: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def payload(self) -> dict:
        return {
            "parser_version": PARSER_VERSION,
            "book": self.book,
            "tests": self.tests,
            "warnings": self.warnings,
            "unmatched_instructions": self.unmatched_instructions,
            "stats": self.stats,
        }


def content_hash(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(
    path: str,
    slug: str = "",
    ocr_engine=None,
    first_page: int | None = None,
    last_page: int | None = None,
    progress=None,
) -> ImportResult:
    """Parse a book into a draft payload."""
    result = ImportResult()

    def say(message: str) -> None:
        if progress:
            progress(message)

    say("reading pages")
    pages_raw: dict[int, list] = {}
    page_sources: dict[int, str] = {}
    page_sizes: dict[int, tuple[float, float]] = {}
    page_height = 0.0
    page_width = 0.0
    for page in pdfsource.load_pages(path, ocr_engine, first_page, last_page):
        page_height = max(page_height, page.height)
        page_width = max(page_width, page.width)
        page_sources[page.number] = page.source
        page_sizes[page.number] = (page.width, page.height)
        pages_raw[page.number] = read_page(page.words, page.width)

    needing_ocr = [n for n, source in page_sources.items()
                   if source == pdfsource.OCR and not pages_raw[n]]
    if needing_ocr:
        result.warnings.append(
            f"{len(needing_ocr)} page(s) have no text layer and no OCR engine was "
            f"available: {needing_ocr[:10]}{'...' if len(needing_ocr) > 10 else ''}"
        )

    say("stripping running headers and footers")
    pages = strip_repeated_chrome(
        pages_raw, page_height or 800.0, protect=is_structural_anchor
    )

    say("segmenting into tests and question groups")
    document = segment(pages)
    result.warnings.extend(document.warnings)

    say("parsing question groups")
    unmatched: list[str] = []
    total_groups = 0
    flagged_groups = 0

    for test in document.tests:
        test_payload: dict = {"number": test.number, "modules": []}
        for skill in (READING, LISTENING):
            module = test.modules.get(skill)
            if module is None:
                continue
            module_payload: dict = {"kind": skill, "sections": []}
            for section in module.sections:
                section_payload: dict = {
                    "order": section.order,
                    "label": _section_label(skill, section.order),
                    "title": section.title,
                    "page_start": section.page_start,
                    "page_end": section.page_end,
                    "groups": [],
                }
                if skill == READING:
                    section_payload["passage_text"] = _passage_text(section)
                    section_payload["passage_regions"] = passage_regions(
                        section, pages, page_sizes
                    )
                    if not section_payload["passage_regions"]:
                        result.warnings.append(
                            f"Test {test.number} Reading Passage {section.order}: no "
                            f"passage region found; the retyped text will be shown"
                        )
                for span in section.groups:
                    classification = classify(span.instruction)
                    if classification.type == bp.UNKNOWN and span.instruction.strip():
                        unmatched.append(normalise_instruction(span.instruction))
                    parsed = parse_group(span, classification)
                    total_groups += 1
                    if parsed.needs_review:
                        flagged_groups += 1
                    section_payload["groups"].append(_group_payload(parsed))
                module_payload["sections"].append(section_payload)
            test_payload["modules"].append(module_payload)
        result.tests.append(test_payload)

    say("parsing answer keys")
    _attach_answer_keys(document, result)

    result.book = {
        "slug": slug,
        "source_pdf": path,
        "content_hash": content_hash(path),
        "page_width": page_width,
        "page_height": page_height,
    }
    result.unmatched_instructions = sorted(set(unmatched))
    result.stats = {
        "pages": len(pages_raw),
        "pages_with_text": sum(1 for s in page_sources.values() if s == pdfsource.NATIVE),
        "pages_ocr": sum(1 for s in page_sources.values() if s == pdfsource.OCR),
        "tests": len(document.tests),
        "groups": total_groups,
        "groups_flagged": flagged_groups,
    }
    return result


def _section_label(skill: str, order: int) -> str:
    return f"Part {order}" if skill == LISTENING else f"Reading Passage {order}"


def _passage_text(section) -> str:
    """The passage body: section lines before the first question group.

    ``segment`` already routes lines to the section rather than a group when no
    ``Questions N-M`` header has been seen yet, so this is simply what is left.
    """
    out = []
    for line in section.lines:
        text = " ".join(line.text.split())
        if not text:
            continue
        if bp.PASSAGE_LEAD_IN.search(text):
            continue
        out.append(text)
    return "\n".join(out)


def _group_payload(parsed: ParsedGroup) -> dict:
    return {
        "type": parsed.type,
        "instruction": parsed.instruction,
        "first_question": parsed.first_question,
        "last_question": parsed.last_question,
        "word_limit": parsed.word_limit,
        "select_count": parsed.select_count,
        "letter_range": list(parsed.letter_range) if parsed.letter_range else None,
        "options_reusable": parsed.options_reusable,
        "options": parsed.options,
        "layout": parsed.layout,
        "needs_figure": parsed.needs_figure,
        "needs_review": parsed.needs_review,
        "warnings": parsed.warnings,
        "page_start": parsed.page_start,
        "page_end": parsed.page_end,
        "questions": [
            {
                "number": q.number,
                "prompt_text": q.prompt_text,
                "options": q.options,
            }
            for q in parsed.questions
        ],
    }


def _expected_kinds(module_payload: dict) -> dict[int, str]:
    """Map question number -> the answer kind its group implies.

    The answer-key parser needs this to resolve the ambiguities it cannot settle
    alone: whether a bare "NOT GIVEN" belongs to a TRUE/FALSE or a YES/NO scale,
    and whether a lone "I" is the option letter I or an OCR'd alternatives pipe.
    """
    from exams.marking import LETTER, TEXT, TFNG, YNNG

    kinds: dict[int, str] = {}
    for section in module_payload["sections"]:
        for group in section["groups"]:
            if group["type"] == bp.TFNG:
                kind = TFNG
            elif group["type"] == bp.YNNG:
                kind = YNNG
            elif group["type"] in bp.LETTER_ANSWER_TYPES:
                kind = LETTER
            else:
                kind = TEXT
            for question in group["questions"]:
                kinds[question["number"]] = kind
    return kinds


def _attach_answer_keys(document: Document, result: ImportResult) -> None:
    """Parse the key section and bind it to each module, with cross-validation."""
    key_lines = document.back_matter.get("keys")
    if not key_lines:
        result.warnings.append(
            "no answer key section was found - without it nothing can be published"
        )
        return

    # The key section runs across several pages, one or two per test. Split it
    # back into per-module chunks on the TEST/LISTENING/READING headings.
    chunks = _split_key_section(key_lines)
    if not chunks:
        result.warnings.append("the answer key section could not be split by test")
        return

    for test_payload in result.tests:
        for module_payload in test_payload["modules"]:
            key = (test_payload["number"], module_payload["kind"])
            text = chunks.get(key)
            if not text:
                result.warnings.append(
                    f"Test {key[0]} {key[1]}: no answer key section found"
                )
                module_payload["answer_key_reliable"] = False
                continue

            parsed = keygrammar.parse_answer_key(
                text, total=40, expected_kinds=_expected_kinds(module_payload)
            )
            module_payload["answer_key_reliable"] = parsed.reliable
            for warning in parsed.warnings:
                result.warnings.append(f"Test {key[0]} {key[1]}: {warning}")

            for section in module_payload["sections"]:
                for group in section["groups"]:
                    for question in group["questions"]:
                        answer = parsed.keys.get(question["number"])
                        if answer is None:
                            question["answer_key"] = None
                            question["raw_key_text"] = ""
                            continue
                        question["answer_key"] = {
                            "kind": answer.kind,
                            "accepted": list(answer.accepted),
                            "set_id": answer.set_id,
                            "set_numbers": list(answer.set_numbers),
                            "select_count": answer.select_count,
                        }
                        question["raw_key_text"] = parsed.raw.get(question["number"], "")


def _split_key_section(lines) -> dict[tuple[int, str], str]:
    """Split the answer-key back matter into (test number, skill) chunks."""
    import re

    test_re = re.compile(r"^test\s+(\d+)\s*$", re.IGNORECASE)
    skill_re = re.compile(r"^(listening|reading)\b", re.IGNORECASE)

    chunks: dict[tuple[int, str], list[str]] = {}
    current_test: int | None = None
    current_skill: str | None = None

    for line in lines:
        text = " ".join(line.text.split())
        if not text:
            continue
        head = text.split(" - ")[0].strip()
        match = test_re.match(head)
        if match:
            current_test = int(match.group(1))
            current_skill = None
            continue
        # "TEST 1 LISTENING" and "TEST 1 I READING" both occur.
        combined = re.match(r"^test\s+(\d+)\s+\w*\s*(listening|reading)\b", text, re.IGNORECASE)
        if combined:
            current_test = int(combined.group(1))
            current_skill = combined.group(2).lower()
            chunks.setdefault((current_test, current_skill), [])
            continue
        skill_match = skill_re.match(text)
        if skill_match and current_test is not None:
            current_skill = skill_match.group(1).lower()
            chunks.setdefault((current_test, current_skill), [])
            continue
        if current_test is not None and current_skill is not None:
            chunks[(current_test, current_skill)].append(text)

    return {key: " ".join(value) for key, value in chunks.items() if value}
