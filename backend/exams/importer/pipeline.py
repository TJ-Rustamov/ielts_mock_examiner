"""Orchestrator: PDF in, reviewable draft payload out.

Runs the stages in order and collects warnings rather than failing. A book that
parses badly must still produce a draft an admin can correct — the one outcome
that is never acceptable is a confident, wrong answer key.

No Django imports, so the whole pipeline can be exercised from a plain script.
"""

from __future__ import annotations

import hashlib
import re
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
    match_anchor,
    segment,
)

__all__ = ["ImportResult", "run", "content_hash"]

#: Bumped whenever a change would make an old draft worth redoing. 1.1: OCR on
#: uploads, embedded-layer detection, column re-read of key pages, self-checks.
PARSER_VERSION = "1.1.0"


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
    # Words of pages this run OCR'd itself, kept so a key page's column
    # re-read can find its gutters without recognising the page a third time.
    ocr_words: dict[int, list] = {}
    page_height = 0.0
    page_width = 0.0
    for page in pdfsource.load_pages(path, ocr_engine, first_page, last_page):
        page_height = max(page_height, page.height)
        page_width = max(page_width, page.width)
        page_sources[page.number] = page.source
        page_sizes[page.number] = (page.width, page.height)
        pages_raw[page.number] = read_page(page.words, page.width)
        if page.source == pdfsource.OCR and page.words:
            ocr_words[page.number] = page.words

    needing_ocr = [n for n, source in page_sources.items()
                   if source == pdfsource.OCR and not pages_raw[n]]
    if needing_ocr:
        result.warnings.append(
            f"{len(needing_ocr)} page(s) have no text layer and no OCR engine was "
            f"available: {needing_ocr[:10]}{'...' if len(needing_ocr) > 10 else ''}"
        )
    embedded = sorted(n for n, source in page_sources.items() if source == pdfsource.EMBEDDED)
    if embedded:
        result.warnings.append(
            f"{len(embedded)} page(s) are scans carrying someone else's OCR layer; "
            "their text is treated as recognised, not typeset, and the answer-key "
            "pages among them are re-read and cross-checked"
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
    _attach_transcripts(document, result)
    _attach_answer_keys(
        document, result, pages, page_sources, path, ocr_engine, ocr_words, say
    )

    say("checking the answer keys")
    _check_answer_keys(result)

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
        "pages_embedded_ocr": len(embedded),
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


_SCRIPT_TEST = re.compile(r"^test\s*(\d+)\b", re.IGNORECASE)
_SCRIPT_PART = re.compile(r"^(?:part|section)\s*(\d+)(?!\d)", re.IGNORECASE)


def _split_script_section(lines) -> dict[tuple[int, int], str]:
    """Split the audioscripts into ``{(test, part): text}``.

    Cambridge prints every recording in full at the back of the book. Nothing
    shows it to candidates; it is the source the Listening answers were taken
    from, which is what makes it useful for checking them.
    """
    chunks: dict[tuple[int, int], list[str]] = {}
    test: int | None = None
    part: int | None = None
    for line in lines:
        text = " ".join(line.text.split())
        if not text:
            continue
        match = match_anchor(_SCRIPT_TEST, text)
        if match and len(text) <= 12:
            test, part = int(match.group(1)), None
            continue
        match = match_anchor(_SCRIPT_PART, text)
        if match and len(text) <= 12:
            part = int(match.group(1))
            continue
        if test is not None and part is not None:
            chunks.setdefault((test, part), []).append(text)
    return {key: "\n".join(value) for key, value in chunks.items()}


def _attach_transcripts(document: Document, result: ImportResult) -> None:
    """Give each Listening part its audioscript, for the answer checks only."""
    lines = document.back_matter.get("scripts")
    if not lines:
        return
    scripts = _split_script_section(lines)
    for test_payload in result.tests:
        for module_payload in test_payload["modules"]:
            if module_payload["kind"] != LISTENING:
                continue
            for section in module_payload["sections"]:
                text = scripts.get((test_payload["number"], section["order"]))
                if text:
                    section["transcript_text"] = text


def _check_answer_keys(result: ImportResult) -> None:
    """Run the self-checks over every module's key and record the verdicts.

    A correction is applied only to a recognised key and only when OCR shape
    confusions explain every difference from the passage; anything else is
    left as a suggestion for the reviewer.
    """
    from exams import keycheck

    for test_payload in result.tests:
        for module_payload in test_payload["modules"]:
            groups = keycheck.groups_from_payload(module_payload)
            lexicons = keycheck.lexicons_from_payload(module_payload)
            answers: dict[int, dict] = {}
            questions: dict[int, dict] = {}
            for section in module_payload["sections"]:
                for group in section["groups"]:
                    for question in group["questions"]:
                        questions[question["number"]] = question
                        if question.get("answer_key"):
                            answers[question["number"]] = question["answer_key"]
            if not questions:
                continue
            evidence = {n: a.get("evidence") for n, a in answers.items()}
            total = max(40, max(questions))
            reports = keycheck.check_module(groups, answers, evidence, lexicons, total=total)
            corrected = []
            for number, question in questions.items():
                report = reports[number]
                answer = question.get("answer_key")
                if answer and report.correction and report.correction.get("explained") \
                        and (answer.get("evidence") or {}).get("source") in (KEY_OCR, KEY_EMBEDDED):
                    answer.setdefault("evidence", {})["ocr_accepted"] = list(answer["accepted"])
                    answer["accepted"] = list(report.correction["to"])
                    corrected.append(number)
                if answer:
                    answer["check"] = report.to_json()
            reports_here = {n: reports[n] for n in questions}
            module_payload["trust"] = keycheck.summarise(reports_here)
            if corrected:
                result.warnings.append(
                    f"Test {test_payload['number']} {module_payload['kind']}: corrected "
                    f"OCR letter confusions in {corrected[:12]} to the spelling printed "
                    "in the passage"
                )


#: Answer-key sources, from the most to the least trustworthy. The label is
#: what the review screen shows and what the self-checks key their rules on.
KEY_TEXT = "text"          # a typeset text layer
KEY_EMBEDDED = "embedded"  # a scan's own OCR layer, from some other engine
KEY_OCR = "ocr"            # recognised by this importer

_SOURCE_LABELS = {
    pdfsource.NATIVE: KEY_TEXT,
    pdfsource.EMBEDDED: KEY_EMBEDDED,
    pdfsource.OCR: KEY_OCR,
}

#: Which read supplies an answer, in order, per source. On a typeset page the
#: flat scanner has the track record (40/40 on seven of Cambridge 21's eight
#: key pages) and nothing else may override it. On a scan with an embedded
#: layer that layer still leads - it is what produced those 40/40s - and the
#: column re-read fills what it withheld. On a scan this importer read itself,
#: the page's own lines read row by row lead: on Cambridge 19 they came out one
#: clean row per answer, where the narrow column strips made OCR stack a run of
#: numbers into one box. Rows welded across a gutter are refused by the row
#: parser, and the column read fills exactly those - and is the cross-check
#: for everything else. The flat scanner comes last: on a page whose sidebar
#: sits beside the answers it reads straight through them.
_READ_ORDER = {
    KEY_TEXT: ("layer",),
    KEY_EMBEDDED: ("layer", "columns", "layer_rows"),
    KEY_OCR: ("layer_rows", "columns", "layer"),
}


def _attach_answer_keys(
    document: Document,
    result: ImportResult,
    pages: dict | None = None,
    page_sources: dict[int, str] | None = None,
    path: str = "",
    ocr_engine=None,
    ocr_words: dict[int, list] | None = None,
    say=None,
) -> None:
    """Parse the key section and bind it to each module, with cross-validation.

    Each module's key is read up to three ways - the flat scanner and the row
    parser over the page text, and for scanned pages a column-by-column OCR
    re-read - and every answer records which read supplied it, whether the
    reads agree, how confident recognition was and where on the page it sits.
    """
    pages = pages or {}
    page_sources = page_sources or {}
    key_lines = document.back_matter.get("keys")
    if not key_lines:
        result.warnings.append(
            "no answer key section was found - without it nothing can be published"
        )
        return

    line_page = {id(line): number for number, lines in pages.items() for line in lines}

    def page_of(line) -> int | None:
        return line_page.get(id(line))

    # The key section runs across several pages, one or two per test. Split it
    # back into per-module chunks on the TEST/LISTENING/READING headings.
    layer_chunks, page_start = _split_key_items(key_lines, page_of=page_of)
    if not layer_chunks:
        result.warnings.append("the answer key section could not be split by test")
        return

    key_pages = sorted({p for p in (page_of(line) for line in key_lines) if p is not None})
    column_chunks = _reread_key_pages(
        key_pages, page_sources, page_start, path, ocr_engine, ocr_words or {},
        result, say,
    )

    for test_payload in result.tests:
        for module_payload in test_payload["modules"]:
            key = (test_payload["number"], module_payload["kind"])
            lines = layer_chunks.get(key)
            if not lines:
                result.warnings.append(
                    f"Test {key[0]} {key[1]}: no answer key section found"
                )
                module_payload["answer_key_reliable"] = False
                continue
            _bind_module_key(
                key, module_payload, lines, page_of, page_sources,
                column_chunks.get(key), result,
            )


def _reread_key_pages(key_pages, page_sources, page_start, path, ocr_engine,
                      ocr_words, result, say) -> dict:
    """Column-by-column OCR of the key pages that were themselves recognised."""
    reread = [p for p in key_pages if page_sources.get(p) in pdfsource.RECOGNISED]
    if not reread:
        return {}
    if ocr_engine is None or not path:
        result.warnings.append(
            "the answer-key pages are scanned, but no OCR engine is available for "
            "the column-by-column re-read that cross-checks them"
        )
        return {}
    if say:
        say(f"re-reading {len(reread)} answer-key page(s) column by column")

    from exams import keysheet

    rows = []
    try:
        for number, png, width, height in pdfsource.render_pages(path, reread):
            read = keysheet.ocr_columns(
                png, ocr_engine, width, height,
                # Reusing this run's own OCR words is only valid when they came
                # from the same preprocessing of the same render.
                words=ocr_words.get(number),
            )
            rows.extend(keysheet.rows_from_columns(read, page=number))
    except Exception as exc:  # never let the cross-check sink the import
        result.warnings.append(f"the column re-read of the key pages failed: {exc}")
        return {}
    chunks, _ = _split_key_items(rows, page_of=lambda row: row.page, start_states=page_start)
    return chunks


def _line_rows(lines, page_of) -> list:
    """Key rows from page lines, with a column index estimated per page.

    Where the question numbers show two or more columns, each line is first
    cut at the column dividers. Whole-page OCR on Cambridge 19 read "2 cotton"
    and the "B" level with it in the next column as one line; a lone letter
    is not a question number, so nothing downstream could tell it had been
    welded on. Cutting by position can.
    """
    from exams import keysheet

    by_page: dict = {}
    for line in lines:
        by_page.setdefault(page_of(line), []).append(line)

    split_rows: list = []
    unsplit: list = []
    for page, page_lines in by_page.items():
        words = [w for line in page_lines for w in line.words]
        width = max((w.x1 for w in words), default=0.0) * 1.05
        dividers = keysheet.number_dividers(words, width) if words else []
        if not dividers:
            unsplit.extend(page_lines)
            continue
        edges = [float("-inf"), *dividers, float("inf")]
        for line in page_lines:
            for column, (left, right) in enumerate(zip(edges[:-1], edges[1:])):
                part = [w for w in line.words if left <= w.x0 < right]
                if not part:
                    continue
                split_rows.append(keygrammar.KeyRow(
                    text=" ".join(" ".join(w.text for w in part).split()),
                    confidence=min(w.confidence for w in part),
                    page=page,
                    bbox=(min(w.x0 for w in part), min(w.y0 for w in part),
                          max(w.x1 for w in part), max(w.y1 for w in part)),
                    column=column,
                ))
    # Column by column, top to bottom: the order a reader takes.
    split_rows.sort(key=lambda row: (row.page or 0, row.column, row.bbox[1]))
    rows = split_rows + _unsplit_rows(unsplit, page_of)
    rows.sort(key=lambda row: row.page or 0)  # stable: keeps each page's order
    return rows


def _unsplit_rows(lines, page_of) -> list:
    """Rows for pages whose columns could not be found: one row per line."""
    by_page: dict = {}
    for line in lines:
        by_page.setdefault(page_of(line), []).append(line)
    columns: dict[int, int] = {}
    for page, page_lines in by_page.items():
        starts = sorted(
            line.x0 for line in page_lines
            if line.words and keygrammar._ROW_NUMBER.match(" ".join(line.text.split()))
        )
        width = max((line.x1 for line in page_lines if line.words), default=0.0)
        clusters: list[float] = []
        for x in starts:
            if not clusters or x - clusters[-1] > max(width * 0.12, 20.0):
                clusters.append(x)
        for line in page_lines:
            if not line.words:
                continue
            index = 0
            for i, start in enumerate(clusters):
                if line.x0 >= start - 4.0:
                    index = i
            columns[id(line)] = index
    rows = []
    for line in lines:
        if not line.words:
            continue
        rows.append(keygrammar.KeyRow(
            text=" ".join(line.text.split()),
            confidence=min(w.confidence for w in line.words),
            page=page_of(line),
            bbox=(line.x0, line.y0, line.x1, line.y1),
            column=columns.get(id(line), 0),
        ))
    return rows


def _key_signature(answer) -> tuple:
    """What two reads must share to count as agreeing."""
    values = {" ".join(str(a).lower().split()) for a in answer.accepted}
    return (answer.kind == "letter_set", tuple(sorted(values)))


def _bind_module_key(key, module_payload, lines, page_of, page_sources,
                     column_rows, result) -> None:
    kinds = _expected_kinds(module_payload)
    label = f"Test {key[0]} {key[1]}"

    chunk_sources = {page_sources.get(page_of(line)) for line in lines} - {None}
    if pdfsource.OCR in chunk_sources:
        source = KEY_OCR
    elif pdfsource.EMBEDDED in chunk_sources:
        source = KEY_EMBEDDED
    else:
        source = KEY_TEXT

    text = " ".join(" ".join(line.text.split()) for line in lines)
    reads: dict[str, keygrammar.KeyParseResult] = {
        "layer": keygrammar.parse_answer_key(text, total=40, expected_kinds=kinds),
        "layer_rows": keygrammar.parse_answer_rows(
            _line_rows(lines, page_of), total=40, expected_kinds=kinds
        ),
    }
    if column_rows:
        reads["columns"] = keygrammar.parse_answer_rows(
            column_rows, total=40, expected_kinds=kinds
        )

    order = [name for name in _READ_ORDER[source] if name in reads]
    primary = reads[order[0]]
    # The parsers' own notes quote the answer text ("Q6: read twice ('10/ten'
    # and ...)"), which would spoil the test for anyone who reads the import
    # job's warnings and then sits it. They go with the module, where only the
    # answer sheet shows them; the job-level warnings carry numbers only.
    module_payload["key_notes"] = [f"{label}: {w}" for w in primary.warnings]
    if not primary.reliable:
        result.warnings.append(
            f"{label}: the key pages did not parse cleanly - see the answer sheet"
        )

    chosen: dict[int, tuple[str, object]] = {}
    for number in range(1, 41):
        for name in order:
            read = reads[name]
            if number in read.keys and number not in read.conflicts:
                chosen[number] = (name, read.keys[number])
                break

    # Agreement between reads that saw the page differently: the column
    # re-read against either reading of the layer. Flat vs rows over the same
    # text proves only that the two parsers agree, so it is not counted.
    independent = source == KEY_EMBEDDED
    disagreements: list[int] = []
    filled: list[int] = []
    evidence_by_number: dict[int, dict] = {}
    for number, (name, answer) in chosen.items():
        raws = {
            read_name: read.raw.get(number, "")
            for read_name, read in reads.items() if number in read.keys
        }
        agreement = None
        columns = reads.get("columns")
        if columns is not None and number in columns.keys:
            layer_answers = [
                reads[n].keys[number] for n in ("layer", "layer_rows")
                if number in reads[n].keys
            ]
            if layer_answers:
                ours = _key_signature(columns.keys[number])
                agreement = (
                    "agree" if any(_key_signature(a) == ours for a in layer_answers)
                    else "disagree"
                )
                if agreement == "disagree":
                    disagreements.append(number)
        if name != order[0]:
            filled.append(number)

        confidence = None
        for read_name in (name, "columns", "layer_rows"):
            read = reads.get(read_name)
            if read is not None and number in read.confidence:
                confidence = read.confidence[number]
                break
        if source == KEY_TEXT:
            confidence = None  # typeset text has no recognition confidence
        crop = None
        for read_name in ("columns", "layer_rows"):
            read = reads.get(read_name)
            if read is not None and number in read.crops:
                crop = read.crops[number]
                break

        evidence_by_number[number] = {
            "source": source,
            "read": name,
            "confidence": confidence,
            "reads": raws,
            "agreement": agreement,
            "independent": independent if agreement else None,
            "filled": name != order[0],
            "crop": crop,
        }

    missing = [n for n in range(1, 41) if n not in chosen]
    question_numbers = {
        q["number"] for section in module_payload["sections"]
        for group in section["groups"] for q in group["questions"]
    }
    missing_here = [n for n in missing if n in question_numbers]
    if missing_here:
        result.warnings.append(
            f"{label}: no answer could be read for question(s) {missing_here}"
        )
    if filled:
        result.warnings.append(
            f"{label}: {len(filled)} answer(s) came from a second reading "
            f"of the key page {filled[:12]} - check them"
        )
    if disagreements:
        result.warnings.append(
            f"{label}: the two readings of the key page disagree on {disagreements[:12]}"
        )

    if source == KEY_TEXT:
        module_payload["answer_key_reliable"] = primary.reliable
    else:
        module_payload["answer_key_reliable"] = not missing_here and not disagreements
    module_payload["key_reads"] = {
        "source": source,
        "primary": order[0],
        "reads": sorted(reads),
        "found": len(chosen),
        "filled": filled,
        "disagreements": disagreements,
    }

    for section in module_payload["sections"]:
        for group in section["groups"]:
            for question in group["questions"]:
                entry = chosen.get(question["number"])
                if entry is None:
                    question["answer_key"] = None
                    question["raw_key_text"] = ""
                    continue
                name, answer = entry
                question["answer_key"] = {
                    "kind": answer.kind,
                    "accepted": list(answer.accepted),
                    "set_id": answer.set_id,
                    "set_numbers": list(answer.set_numbers),
                    "select_count": answer.select_count,
                    "evidence": evidence_by_number.get(question["number"]),
                }
                question["raw_key_text"] = reads[name].raw.get(question["number"], "")


_KEY_TEST = re.compile(r"^test\s*(\d+)\s*$", re.IGNORECASE)
# Not "Listening and Reading answer keys", the running header of every key page.
_KEY_SKILL = re.compile(r"^(listening|reading)\b(?!\s*and\b)", re.IGNORECASE)
_KEY_COMBINED = re.compile(r"^test\s*(\d+)\s*\w*?\s*(listening|reading)\b", re.IGNORECASE)


def _split_key_items(items, page_of=None, start_states=None):
    """Split key lines (or rows) into ``{(test, skill): [items]}``.

    Also returns, per page, the chunk its first content line belongs to.
    `start_states` feeds that back in when splitting a second reading of the
    same pages: a column re-read often cuts a heading in half, so a page
    starts in the chunk the first reading saw, and any heading the re-read did
    catch switches it from there.
    """
    chunks: dict[tuple[int, str], list] = {}
    page_start: dict = {}
    current_test: int | None = None
    current_skill: str | None = None
    last_page = object()

    for item in items:
        text = " ".join(item.text.split())
        if not text:
            continue
        page = page_of(item) if page_of else None
        if page != last_page:
            last_page = page
            if start_states and page in start_states:
                current_test, current_skill = start_states[page]

        head = text.split(" - ")[0].strip()
        match = match_anchor(_KEY_TEST, head)
        if match:
            number = int(match.group(1))
            # "TEST 1" also runs at the top of the page. Reading order can put
            # it after the skill heading, or a column re-read can meet it
            # partway down; the same test number again is not a new section.
            if number != current_test:
                current_skill = None
            current_test = number
            continue
        # "TEST 1 LISTENING" and "TEST 1 I READING" both occur.
        combined = match_anchor(_KEY_COMBINED, text)
        if combined:
            current_test = int(combined.group(1))
            current_skill = combined.group(2).lower()
            continue
        skill_match = match_anchor(_KEY_SKILL, text)
        if skill_match and current_test is not None:
            current_skill = skill_match.group(1).lower()
            continue
        if current_test is not None and current_skill is not None:
            chunk = (current_test, current_skill)
            chunks.setdefault(chunk, []).append(item)
            if page is not None and page not in page_start:
                page_start[page] = chunk

    return {key: value for key, value in chunks.items() if value}, page_start


def _split_key_section(lines) -> dict[tuple[int, str], str]:
    """Split the answer-key back matter into (test number, skill) text chunks."""
    chunks, _ = _split_key_items(lines)
    return {
        key: " ".join(" ".join(line.text.split()) for line in value)
        for key, value in chunks.items()
    }
