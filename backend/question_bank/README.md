# Question bank

Raw question data, kept as files so it can be checked, edited and reloaded.

## speaking/

| File | What it is |
|---|---|
| `q2.txt` | Part 1 topics, Part 2 cue cards and Part 3 topics, as plain text |
| `q1.txt` | 50 complete test sets (Part 1 questions, a cue card and its own Part 3 questions) |
| `parse_q2.py`, `parse_q1.py` | Turn the text files into the JSON files below |
| `q2_tests.json`, `q1_tests.json` | Parsed questions; this is what gets loaded |

From `q1.txt` only the cue cards and their Part 3 questions are kept: its Part 1
questions have no topic names. Each cue card and its Part 3 share one topic name,
which is how the examiner follows a card with the right discussion.

After editing a text file, re-parse and reload:

```powershell
python backend/question_bank/speaking/parse_q2.py
python backend/question_bank/speaking/parse_q1.py
docker exec ielts_backend python manage.py load_speaking_questions --replace
```

`load_speaking_questions` without `--replace` only adds what is new, so it is safe
to run again. `--replace` also removes questions added by hand in
Admin → Speaking Questions.

## reading/ and listening/

Generated from the database, one file per book:

```powershell
docker exec ielts_backend python manage.py export_exams
```

Each file has the same shape the book importer produces, with every question's
confirmed answer key, so it can be published back into a fresh database without
re-running OCR on the book (the keys then need confirming again). These folders
are not committed: like `materials/`, they contain the books' full passages and
answer keys.
