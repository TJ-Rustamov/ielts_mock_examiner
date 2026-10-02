"""Verbatim answer-key text from Cambridge IELTS 21, PDF pages 117-124.

Extracted from the book own OCR text layer and committed as-is, OCR artefacts
included, so the key parser is tested against what it will really be given
rather than a cleaned-up ideal. The PDFs are far too large to commit; this
text is a few KB.

T2_LISTENING (page 119) is deliberately included even though it cannot be
parsed: its columns interleave in the source, and the parser is expected to
detect that and refuse rather than emit a wrong key.
"""

T1_LISTENING = (
    "Listening and Reading answer keys TEST 1 LISTENING - Answer key with extra "
    "explanations - in Resource Bank Part 1, Questions 1-10 1 10/ten 2 weather 3 safety 4 "
    "discount 5 dictionary 6 certificate 7 towel 8 cafe I cafe 9 videos 10 Lockers Part "
    "2, Questions 11-20 11 A 12 B 13 A 14 A 15 A 16 C 17 C 18 A 19 B 20 C If you score "
    "... 0-19 you are unlikely to get an acceptable score under examination conditions "
    "and we recommend that you spend a lot of time improving your English before you take "
    "IELTS. 20-28 Part 3, Questions 21-30 21 &22 IN EITHER ORDER B D 23&24 IN EITHER "
    "ORDER C E 25 G 26 B 27 F 28 H 29 A 30 E Part 4, Questions 31-40 31 metal(s) 32 slow "
    "33 demand 34 equator 35 recycle 36 fungus 37 weather 38 strong 39 roots 40 soil "
    "29-40 you may get an acceptable you are likely to get an score under examination "
    "acceptable score under conditions but we recommend examination conditions but that "
    "you think about having remember that different more practice or lessons before "
    "institutions will find different you take IELTS. scores acceptable. 117"
)

T1_READING = (
    "Listening and Reading answer keys TEST 1 I READING - Answer key with extra "
    "explanations g in Resource Bank Reading Passage 1, Questions 1-13 1 mining 2 "
    "education 3 notes 4 journals 5 Venice 6 canteen 7 friends 8 TRUE 9 NOTGIVEN 10 FALSE "
    "11 NOT GIVEN 12 TRUE 13 TRUE Reading Passage 2, Questions 14-26 14 C 15 B 16 A 17 G "
    "18 breath 19 questionnaire 20 wellbeing If you score ... 0-18 you are unlikely to "
    "get an acceptable score under examination conditions and we recommend that you spend "
    "a lot of time improving your English before you take IELTS. 118 21 depression 22 C "
    "23 A 24 B 25 D 26 C Reading Passage 3, Questions 27-40 27 B 28 A 29 C 30 A 31 H 32 E "
    "33 I 34 A 35 G 36 C 37 YES 38 NOTGIVEN 39 NO 40 YES 19-27 28-40 you may get an "
    "acceptable you are likely to get an score under examination acceptable score under "
    "conditions but we recommend examination conditions but that you think about having "
    "remember that different more practice or lessons before institutions will find "
    "different you take IELTS. scores acceptable."
)

T2_LISTENING = (
    "Listening and Reading answer keys TEST 2 LISTENING - Answer key with extra "
    "explanations - in Resource Bank Part 1, Questions 1-10 1 (the) 13(th) (of) January/ "
    "13.01 / 13.1 2 48 I forty-eight Part 3, Questions 21-30 21 &22 IN EITHER ORDER 3 "
    "pizza 4 India 5 mirror B E 23&24 IN EITHER ORDER C 6 (the) 6(th) (of) April / 06.04 "
    "I 6.4 7 natural D 25&26 IN EITHER ORDER A 8 67.50 I sixty-seven fifty 9 shirt 10 "
    "hammer Part 2, Questions 11-20 11 &12 IN EITHER ORDER B E 13&14 IN EITHER ORDER C D "
    "15 F 16 B 17 D 18 A 19 H 20 E If you score ... 0-19 you are unlikely to get an "
    "acceptable score under examination conditions and we recommend that you spend a lot "
    "of time improving your English before you take IELTS. C 27 C 28 D 29 F 30 A Part 4, "
    "Questions 31-40 31 Pollution 20-28 32 tax 33 chocolate 34 timing 35 cost 36 rules 37 "
    "diving 38 vegan 39 wifi 40 videos you may get an acceptable score under examination "
    "conditions but we recommend that you think about having more practice or lessons "
    "before you take IELTS. 29-40 you are likely to get an acceptable score under "
    "examination conditions but remember that different institutions will find different "
    "scores acceptable. 119"
)

T2_READING = (
    "Listening and Reading answer keys TEST 2 READING  Answer key with extra "
    "explanations in Resource Bank Reading Passage 1, Questions 1-13 1 rats 2 visual 3 "
    "half 4 temperature 5 vivid 6 TRUE 7 FALSE 8 NOTGIVEN 9 FALSE 10 TRUE 11 FALSE 12 "
    "NOTGIVEN 13 NOTGIVEN Reading Passage 2, Questions 14-26 14 E 15 G 16 C 17 D 18 B 19 "
    "A 20&21 IN EITHER ORDER B D If you score ... 0-19 you are unlikely to get an "
    "acceptable score under examination conditions and we recommend that you spend a lot "
    "of time improving your English before you take IELTS. 120 22 prosperity 23 whistles "
    "24 bodies 25 ancestors 26 jewellery I jewelry Reading Passage 3, Questions 27-40 27 "
    "B 28 A 29 C 30 F 31 G 32 I 33 C 34 A 35 D 36 NO 37 NOTGIVEN 38 NO 39 YES 40 B 20-28 "
    "29-40 you may get an acceptable you are likely to get an score under examination "
    "acceptable score under conditions but we recommend examination conditions but that "
    "you think about having remember that different more practice or lessons before "
    "institutions will find different you take IELTS. scores acceptable."
)

T3_LISTENING = (
    "Listening and Reading answer keys TEST 3 LISTENING  Answer key with extra "
    "explanations in Resource Bank Part 1, Questions 1-10 1 Northern 2 week 3 250 I two "
    "hundred and fifty 4 voucher 5 window 6 books 7 blanket 8 dolphins 9 Drum 10 Italian "
    "Part 2, Questions 11-20 11 &12 IN EITHER ORDER C E 13&14 IN EITHER ORDER B E 15 B 16 "
    "C 17 F 18 A 19 B 20 D If you score ... 0-18 you are unlikely to get an acceptable "
    "score under examination conditions and we recommend that you spend a lot of time "
    "improving your English before you take IELTS. 19-27 Part 3, Questions 21-30 21 &22 "
    "IN EITHER ORDER B D 23&24 IN EITHER ORDER D E 25 G 26 B 27 F 28 A 29 H 30 D Part 4, "
    "Questions 31-40 31 disease 32 ecosystem 33 holiday(s) 34 pets 35 sugar 36 light 37 "
    "virus 38 behaviour/ behavior 39 database 40 photograph 28-40 you may get an "
    "acceptable you are likely to get an score under examination acceptable score under "
    "conditions but we recommend examination conditions but that you think about having "
    "remember that different more practice or lessons before institutions will find "
    "different you take IELTS. scores acceptable. 121"
)

T3_READING = (
    "Listening and Reading answer keys TEST 3 READING Ill Answer key with extra "
    "explanations - in Resource Bank Reading Passage 1, Questions 1-13 1 dust 2 blood 3 "
    "coat 4 horns 5 habitat 6 routes 7 streams 8 FALSE 9 FALSE 10 TRUE 11 NOTGIVEN 12 "
    "TRUE 13 NOT GIVEN Reading Passage 2, Questions 14-26 14 NOT GIVEN 15 FALSE 16 "
    "NOTGIVEN 17 TRUE 18 FALSE 19 lanes 20 boarding If you score ... 0-17 you are "
    "unlikely to get an acceptable score under examination conditions and we recommend "
    "that you spend a lot of time improving your English before you take IELTS. 122 21 "
    "wheelchairs 22 fuel 23 flood 24 smartcards 25 gates 26 queues Reading Passage 3, "
    "Questions 27-40 27 A 28 A 29 D 30 A 31 E 32 F 33 D 34 B 35 NO 36 NOT GIVEN 37 NOT "
    "GIVEN 38 YES 39 YES 40 NO 18-26 27-40 you may get an acceptable you are likely to "
    "get an score under examination acceptable score under conditions but we recommend "
    "examination conditions but that you think about having remember that different more "
    "practice or lessons before institutions will find different you take IELTS. scores "
    "acceptable."
)

T4_LISTENING = (
    "Listening and Reading answer keys TEST 4 LISTENING  Answer key with extra "
    "explanations in Resource Bank Part 1, Questions 1-10 1 Leigh 2 motorbike 3 "
    "hairdresser 4 suit 5 laptop 6 Monday 7 coffee 8 books 9 plants 10 cinema Part 2, "
    "Questions 11-20 11 &12 IN EITHER ORDER C E 13&14 IN EITHER ORDER A B 15 C 16 G 17 D "
    "18 A 19 F 20 B If you score ... 0-16 you are unlikely to get an acceptable score "
    "under examination conditions and we recommend that you spend a lot of time improving "
    "your English before you take IELTS. Part 3, Questions 21-30 21 B 22 A 23 B 24 B 25 E "
    "26 I 27 A 28 D 29 H 30 G Part 4, Questions 31-40 31 routine 17-26 32 trials 33 "
    "calming 34 pillows 35 anxiety 36 medication 37 awake 38 distraction 39 nature 40 "
    "volume you may get an acceptable score under examination conditions but we recommend "
    "that you think about having more practice or lessons before you take IELTS. 27-40 "
    "you are likely to get an acceptable score under examination conditions but remember "
    "that different institutions will find different scores acceptable. 123"
)

T4_READING = (
    "Listening and Reading answer keys TEST 4 READING - Answer key with extra "
    "explanations - in Resource Bank Reading Passage 1, Questions 1-13 1 TRUE 2 FALSE 3 "
    "TRUE 4 NOTGIVEN 5 NOTGIVEN 6 FALSE 7 TRUE 8 cow dung 9 fermentation (process) 10 "
    "pipes 11 time 12 money 13 price Reading Passage 2, Questions 14-26 14 I 15 J 16 H 17 "
    "B 18 E 19 F If you score ... 0-17 you are unlikely to get an acceptable score under "
    "examination conditions and we recommend that you spend a lot of time improving your "
    "English before you take IELTS. 124 18-26 20 NO 21 NOTGIVEN 22 YES 23 NO 24 C 25 D 26 "
    "D Reading Passage 3, Questions 27-40 27 G 28 J 29 I 30 C 31 A 32 E 33 NO 34 NOTGIVEN "
    "35 NOTGIVEN 36 YES 37 B 38 C 39 D 40 A 27-40 you may get an acceptable you are "
    "likely to get an score under examination acceptable score under conditions but we "
    "recommend examination conditions but that you think about having remember that "
    "different more practice or lessons before institutions will find different you take "
    "IELTS. scores acceptable."
)

ALL_KEY_PAGES = {
    117: T1_LISTENING,
    118: T1_READING,
    119: T2_LISTENING,
    120: T2_READING,
    121: T3_LISTENING,
    122: T3_READING,
    123: T4_LISTENING,
    124: T4_READING,
}
