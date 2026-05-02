import re, json

INPUT_FILE  = "q2.txt"
OUTPUT_FILE = "q2_tests.json"

PART_HEADER = re.compile(r"Part ([123]) IELTS Speaking Questions\s*$", re.IGNORECASE)
CUE_VERB    = re.compile(r"^(Describe|Talk about|Tell me about|Please tell me)\b", re.IGNORECASE)

def is_cue(s):
    return bool(CUE_VERB.match(s))

def next_nonblank(lines, i):
    for j in range(i+1, len(lines)):
        s = lines[j].strip()
        if s: return s
    return ""

def split_sections(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        lines = [l.rstrip("\r\n") for l in f]
    sections, current = {}, None
    for line in lines:
        m = PART_HEADER.match(line.strip())
        if m:
            current = int(m.group(1))
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections, lines

def parse_flat(lines):
    """Part 1 & 3: topic = short line followed by blank line."""
    result, current_topic, current_qs = [], None, []

    def flush():
        if current_topic and current_qs:
            result.append({"id": len(result)+1, "topic": current_topic, "questions": list(current_qs)})

    padded = lines + [""]
    for i, line in enumerate(padded[:-1]):
        s          = line.strip()
        next_blank = not padded[i+1].strip()
        if not s: continue
        if next_blank and not s.endswith("?") and not s.startswith("-") and len(s) <= 90:
            flush()
            current_topic = s
            current_qs = []
        else:
            clean = re.sub(r"^-\s*", "", s)
            if clean and current_topic:
                current_qs.append({"id": len(current_qs)+1, "text": clean})
    flush()
    return result

def parse_part2(lines):
    """Part 2: topic = next nonblank is a cue card. Points start with '-'."""
    result = []
    current_topic = None
    in_cue, cue_inst, cue_pts = False, "", []

    def flush_cue():
        nonlocal in_cue, cue_inst, cue_pts
        if cue_inst and current_topic:
            result.append({
                "id":       len(result)+1,
                "topic":    current_topic,
                "cue_card": cue_inst,
                "points":   list(cue_pts)
            })
        in_cue, cue_inst, cue_pts = False, "", []

    for i, line in enumerate(lines):
        s  = line.strip()
        nb = next_nonblank(lines, i)
        if not s: continue

        # Topic heading: next non-blank is a cue instruction, this line is short & plain
        if is_cue(nb) and not is_cue(s) and not s.startswith("-") and len(s) <= 90:
            flush_cue()
            current_topic = s
            continue

        # Cue card instruction
        if is_cue(s):
            flush_cue()
            in_cue, cue_inst, cue_pts = True, s, []
            continue

        # Point (starts with "-")
        if in_cue and s.startswith("-"):
            cue_pts.append({"id": len(cue_pts)+1, "text": s[1:].strip()})
            continue

    flush_cue()
    return result

def main():
    print(f"Parsing '{INPUT_FILE}'...")
    sections, _ = split_sections(INPUT_FILE)

    part1 = parse_flat(sections.get(1, []))
    part2 = parse_part2(sections.get(2, []))
    part3 = parse_flat(sections.get(3, []))

    print(f"  part1 -> {len(part1)} topics")
    print(f"  part2 -> {len(part2)} cue cards")
    print(f"  part3 -> {len(part3)} topics")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"part1": part1, "part2": part2, "part3": part3}, f, ensure_ascii=False, indent=2)

    print(f"  Written to '{OUTPUT_FILE}'.")

if __name__ == "__main__":
    main()
