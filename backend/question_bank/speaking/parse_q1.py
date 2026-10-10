import re, json
from pathlib import Path

# Next to this script, so it runs the same from any folder.
HERE        = Path(__file__).resolve().parent
INPUT_FILE  = HERE / "q1.txt"
OUTPUT_FILE = HERE / "q1_tests.json"

# q1.txt holds complete test sets:
#   IELTS SPEAKING TEST QUESTIONS N
#   Q1..Q5   Part 1 questions (no topic names, so not used here)
#   Q1       the Part 2 cue card ("Describe ...")
#   Q1..Q5   Part 3 questions about that cue card
# Only the cue card and its own Part 3 questions are kept, under one shared
# topic name so the examiner moves from the card to its follow-up discussion.

TEST_HEADER = re.compile(r"^IELTS SPEAKING TEST QUESTIONS\s+(\d+)\s*$", re.IGNORECASE)
Q_MARKER    = re.compile(r"^Q\d+\s*$")
CUE_VERB    = re.compile(r"^(Describe|Talk about|Tell me about)\b", re.IGNORECASE)
# "You should say:", "Please say:" and "You should explain:" all introduce the points.
SHOULD_SAY  = re.compile(r"\b(?:you should|please)\s+(?:say|explain)\s*:?", re.IGNORECASE)


def split_tests(lines):
    tests, current = [], None
    for line in lines:
        s = line.strip()
        m = TEST_HEADER.match(s)
        if m:
            current = {"number": int(m.group(1)), "lines": []}
            tests.append(current)
        elif current is not None:
            current["lines"].append(s)
    return tests


def split_blocks(lines):
    """Each 'Qn' marker starts a block; the block is the lines up to the next marker."""
    blocks, current = [], None
    for s in lines:
        if Q_MARKER.match(s):
            current = []
            blocks.append(current)
        elif current is not None and s:
            current.append(s)
    return [b for b in blocks if b]


def topic_from_cue(cue):
    """'Describe a book that influenced you. You should say: ...' -> 'A book that influenced you'."""
    text = SHOULD_SAY.split(cue)[0]
    text = CUE_VERB.sub("", text).strip(" .,:;")
    return (text[:1].upper() + text[1:])[:120]


def parse_cue(block):
    """The instruction line plus its points, whether bulleted or inline after 'You should say:'."""
    first = block[0]
    points = []
    lead_in = SHOULD_SAY.search(first)
    if lead_in:
        # Keep the book's own wording ("Please say:", "You should explain:").
        instruction = first[:lead_in.end()].strip().rstrip(":") + ":"
        inline = re.sub(r"^-\s*", "", first[lead_in.end():].strip())
        if inline:
            # Points written on one line use one of three separators:
            #   "where you went; how you travelled; and explain ..."
            #   "- Where it was - What it looked like - And explain ..."
            #   "what the book is, how you heard of it, and explain ..."
            # Use the one present, so commas inside a point survive.
            if ";" in inline:
                pieces = inline.split(";")
            elif re.search(r"\s-\s", inline):
                pieces = re.split(r"\s+-\s+", inline)
            else:
                pieces = re.split(r",\s*", inline)
            for piece in pieces:
                piece = piece.strip(" .")
                if piece:
                    points.append(piece)
    else:
        instruction = first.strip()

    for line in block[1:]:
        clean = re.sub(r"^-\s*", "", line).strip()
        if clean:
            points.append(clean.rstrip("."))

    return instruction, [{"id": i + 1, "text": p} for i, p in enumerate(points)]


def main():
    print(f"Parsing '{INPUT_FILE}'...")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        lines = [l.rstrip("\r\n") for l in f]

    part2, part3, skipped = [], [], []
    for test in split_tests(lines):
        blocks = split_blocks(test["lines"])
        cue_index = next((i for i, b in enumerate(blocks) if CUE_VERB.match(b[0])), None)
        if cue_index is None:
            skipped.append(test["number"])
            continue

        instruction, points = parse_cue(blocks[cue_index])
        topic = topic_from_cue(instruction)
        questions = [" ".join(b) for b in blocks[cue_index + 1:]]

        part2.append({"id": len(part2) + 1, "topic": topic, "cue_card": instruction, "points": points})
        if questions:
            part3.append({
                "id": len(part3) + 1,
                "topic": topic,
                "questions": [{"id": i + 1, "text": q} for i, q in enumerate(questions)],
            })

    print(f"  part2 -> {len(part2)} cue cards")
    print(f"  part3 -> {len(part3)} topics")
    if skipped:
        print(f"  skipped (no cue card found): tests {skipped}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"part2": part2, "part3": part3}, f, ensure_ascii=False, indent=2)

    print(f"  Written to '{OUTPUT_FILE}'.")


if __name__ == "__main__":
    main()
