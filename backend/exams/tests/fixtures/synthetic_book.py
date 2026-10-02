"""A small scanned "book" built on the fly: one Listening test, image-only pages.

Question pages, an answer-key page in two columns with a band-score box, and an
audioscript page, each rendered to an image, skewed, shaded and JPEG-damaged
the way a phone scan is, then wrapped in a PDF with no text layer at all. It
exercises the whole scanned-book path - OCR, segmentation, the column re-read
of the key page and the self-checks - without committing a real book.
"""

from __future__ import annotations

ANSWERS = {
    1: "mining", 2: "education", 3: "notes", 4: "journals", 5: "Venice", 6: "10/ten",
    7: "weather", 8: "cafe", 9: "metal(s)", 10: "slow", 11: "A", 12: "B", 13: "A",
    14: "C", 15: "A", 16: "C", 17: "C", 18: "A", 19: "B", 20: "C", 25: "G", 26: "B",
    27: "F", 28: "H", 29: "A", 30: "E", 31: "demand", 32: "equator", 33: "recycle",
    34: "fungus", 35: "roots", 36: "soil", 37: "strong", 38: "harvest", 39: "drought",
    40: "seeds",
}
#: What a correct import must produce, sets included.
TRUTH = {**ANSWERS, 21: "B D", 22: "B D", 23: "C E", 24: "C E"}

WIDTH, HEIGHT = 1654, 2339  # A4 at 200 DPI, a typical scan


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    name = "DejaVuSerif-Bold.ttf" if bold else "DejaVuSerif.ttf"
    for path in (f"/usr/share/fonts/truetype/dejavu/{name}", name):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _page(lines):
    from PIL import Image, ImageDraw

    image = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(image)
    for x, y, text, size, bold in lines:
        draw.text((x, y), text, font=_font(size, bold), fill=0)
    return image


def _question_pages():
    first = [(120, 100, "Test 1", 40, True), (120, 180, "LISTENING", 34, True),
             (120, 260, "PART 1 Questions 1-10", 28, True),
             (120, 320, "Complete the notes below.", 24, False),
             (120, 365, "Write ONE WORD AND/OR A NUMBER for each answer.", 24, False)]
    first += [(160, 430 + (i - 1) * 60, f"Item {i} is about the {i} ..................", 24, False)
              for i in range(1, 11)]
    first += [(120, 1100, "PART 2 Questions 11-20", 28, True),
              (120, 1160, "Choose the correct letter, A, B or C.", 24, False)]

    def mcq(numbers, top):
        out = []
        for index, number in enumerate(numbers):
            y = top + index * 200
            out.append((160, y, f"{number} What does the speaker say about item {number}?", 24, False))
            out += [(200, y + 45 + k * 42, f"{c}   {w} choice", 22, False)
                    for k, (c, w) in enumerate(zip("ABC", ("first", "second", "third")))]
        return out

    first += mcq(range(11, 16), 1220)
    second = mcq(range(16, 21), 100)
    third = [(120, 100, "PART 3 Questions 21-30", 28, True),
             (120, 160, "Questions 21 and 22", 26, True),
             (120, 210, "Choose TWO letters, A-E.", 24, False)]
    third += [(160, 260 + k * 45, f"{c} option {c.lower()}", 22, False) for k, c in enumerate("ABCDE")]
    third += [(120, 520, "Questions 23 and 24", 26, True),
              (120, 570, "Choose TWO letters, A-E.", 24, False)]
    third += [(160, 620 + k * 45, f"{c} choice {c.lower()}", 22, False) for k, c in enumerate("ABCDE")]
    third += [(120, 880, "Questions 25-30", 26, True),
              (120, 930, "Choose SIX answers from the box and write the correct letter, A-H, "
                         "next to Questions 25-30.", 20, False)]
    third += [(160, 980 + k * 45, f"{25 + k} topic {k}", 22, False) for k in range(6)]
    third += [(120, 1300, "PART 4 Questions 31-40", 28, True),
              (120, 1360, "Complete the notes below.", 24, False),
              (120, 1405, "Write ONE WORD ONLY for each answer.", 24, False)]
    third += [(160, 1470 + (i - 31) * 60, f"Fact {i - 30} relates to {i} ..................", 24, False)
              for i in range(31, 41)]
    return [_page(first), _page(second), _page(third)]


def _key_page():
    lines = [(120, 100, "Listening and Reading answer keys", 36, True),
             (120, 170, "TEST 1", 34, True), (120, 230, "LISTENING", 30, True)]
    y = 320
    for heading, numbers in (("Part 1, Questions 1-10", range(1, 11)),
                             ("Part 2, Questions 11-20", range(11, 21))):
        lines.append((120, y, heading, 24, True))
        y += 55
        for n in numbers:
            lines += [(120, y, str(n), 26, True), (190, y, ANSWERS[n], 26, False)]
            y += 50
    x, y = 880, 320
    lines.append((x, y, "Part 3, Questions 21-30", 24, True))
    y += 55
    for pair, letters in (("21&22", "BD"), ("23&24", "CE")):
        lines += [(x, y, pair, 26, True), (x + 110, y, "IN EITHER ORDER", 24, False)]
        y += 50
        for letter in letters:
            lines.append((x + 110, y, letter, 26, False))
            y += 50
    for n in range(25, 31):
        lines += [(x, y, str(n), 26, True), (x + 70, y, ANSWERS[n], 26, False)]
        y += 50
    lines.append((x, y, "Part 4, Questions 31-40", 24, True))
    y += 55
    for n in range(31, 41):
        lines += [(x, y, str(n), 26, True), (x + 70, y, ANSWERS[n], 26, False)]
        y += 50
    lines += [(120, 1980, "If you score ...", 24, True),
              (120, 2030, "0-15 you are unlikely to get an acceptable score under "
                          "examination conditions", 22, False)]
    return _page(lines)


def _script_page():
    part1 = [ANSWERS[n].split("/")[0].replace("(s)", "s") for n in range(1, 11)]
    part4 = [ANSWERS[n] for n in range(31, 41)]
    lines = [(120, 100, "Audioscripts", 36, True), (120, 170, "TEST 1", 32, True),
             (120, 230, "PART 1", 28, True)]
    y = 290
    for a, b in zip(part1[::2], part1[1::2]):
        lines.append((120, y, f"WOMAN: We talked about {a} and then about {b} today.", 22, False))
        y += 48
    lines.append((120, y + 20, "PART 4", 28, True))
    y += 90
    for a, b in zip(part4[::2], part4[1::2]):
        lines.append((120, y, f"LECTURER: Consider {a} first, and later {b} too.", 22, False))
        y += 48
    return _page(lines)


def _degrade(image, skew: float, shadow: tuple[float, float], seed: int) -> bytes:
    import cv2
    import numpy as np

    array = np.asarray(image).astype(np.float32)
    height, width = array.shape
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), skew, 1.0)
    array = cv2.warpAffine(array, matrix, (width, height), borderValue=255)
    array = array * np.linspace(shadow[0], shadow[1], width)[None, :]
    array = cv2.GaussianBlur(array, (3, 3), 0)
    noise = np.random.default_rng(seed).normal(0, 10, array.shape)
    array = np.clip(array + noise, 0, 255).astype(np.uint8)
    ok, encoded = cv2.imencode(".jpg", array, [cv2.IMWRITE_JPEG_QUALITY, 60])
    return encoded.tobytes()


def make_book(path: str, skew: float = 1.2, shadow=(0.6, 0.95), seed: int = 2) -> dict:
    """Write the scanned book to `path`. Returns the true answers."""
    import pymupdf

    document = pymupdf.open()
    images = _question_pages() + [_key_page(), _script_page()]
    for index, image in enumerate(images):
        angle = skew if index % 2 == 0 else -skew * 0.6
        page = document.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=_degrade(image, angle, shadow, seed + index))
    document.save(path)
    document.close()
    return TRUTH


def score(result, truth=TRUTH) -> tuple[int, int, int, dict]:
    """(correct, wrong, missing, {number: wrong answer}) for a pipeline result."""
    keys = {}
    for test in result.tests:
        for module in test["modules"]:
            for section in module["sections"]:
                for group in section["groups"]:
                    for question in group["questions"]:
                        if question.get("answer_key"):
                            keys[question["number"]] = question["answer_key"]
    correct = wrong = 0
    bad = {}
    for number, answer in truth.items():
        key = keys.get(number)
        if not key:
            continue
        got = {a.lower() for a in key["accepted"]}
        if key["kind"] == "letter_set":
            ok = set(answer.lower().split()) == got
        else:
            ok = {a.lower() for a in answer.replace("(s)", "").split("/")} <= got
        if ok:
            correct += 1
        else:
            wrong += 1
            bad[number] = key["accepted"][:3]
    return correct, wrong, len(truth) - correct - wrong, bad
