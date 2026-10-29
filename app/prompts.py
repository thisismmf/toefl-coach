"""Every LLM call in the system.

Design rule: one narrow job per call, a schema stated inline, and JSON out.
Small local models collapse when asked to grade + explain + rewrite at once,
so nothing here ever asks for more than one kind of thing.
"""
from __future__ import annotations

import json

from .rubrics import (BAND_GUIDE, SPEAKING_CRITERIA, SUBSCORES, TASK_LABEL,
                      WRITING_CRITERIA)

RATER_SYS = (
    "You are a strict, experienced ETS-certified TOEFL iBT rater for the 2026 "
    "test format. You are precise, concise, and never generous. "
    "You always reply with valid JSON only - no prose, no markdown fences."
)
COACH_SYS = (
    "You are an expert TOEFL writing and speaking coach. You explain errors by "
    "their underlying rule, not case by case. Your student is a Persian (Farsi) "
    "speaker, so you name first-language interference when it is the real cause. "
    "You always reply with valid JSON only - no prose, no markdown fences."
)


def _criteria(task: str) -> str:
    return SPEAKING_CRITERIA if task == "speaking" else WRITING_CRITERIA


def _context_block(task: str, payload: dict) -> str:
    """Render the task input exactly as the rater needs to see it."""
    if task == "email":
        return (f"EMAIL TASK PROMPT:\n{payload['question']}\n\n"
                f"STUDENT'S EMAIL:\n{payload['response']}")
    if task == "discussion":
        return (f"PROFESSOR'S QUESTION:\n{payload['question']}\n\n"
                f"CLASSMATE A:\n{payload.get('classmate_a', '(none given)')}\n\n"
                f"CLASSMATE B:\n{payload.get('classmate_b', '(none given)')}\n\n"
                f"STUDENT'S POST:\n{payload['response']}")
    return (f"INTERVIEW QUESTION:\n{payload['question']}\n\n"
            f"STUDENT'S SPOKEN ANSWER (transcript):\n{payload['response']}")


def _stats_block(stats: dict) -> str:
    keep = {k: stats[k] for k in (
        "words", "sentences", "avg_sentence_len", "multi_clause_sentences",
        "transitions_found", "advanced_vocab_found", "likely_typos",
        "double_conjunction", "repeated_sentence_starts", "overlong_sentences",
    ) if k in stats}
    for k in ("wpm", "duration_sec", "fillers_found"):
        if k in stats:
            keep[k] = stats[k]
    return ("MEASURED FACTS (already computed - trust these, do not recount):\n"
            + json.dumps(keep, ensure_ascii=False, indent=1))


# ───────────────────────── GRADE pipeline ─────────────────────────

def p_task_check(task: str, payload: dict) -> list[dict]:
    if task == "email":
        job = """Decide whether the student's email satisfies EVERY bullet point in the task prompt.
Return JSON:
{"bullets":[{"bullet":"<the bullet, quoted from the prompt>","addressed":true|false,
  "evidence":"<the exact sentence from the email that does it, or empty>"}],
 "bullets_ok": true|false,
 "register":"formal"|"friendly",
 "register_appropriate": true|false,
 "register_note":"<one sentence>",
 "purpose_clear": true|false,
 "summary":"<one sentence on task completion>"}"""
    elif task == "discussion":
        job = """Judge how the student's post functions inside the discussion.
Return JSON:
{"on_topic": true|false,
 "on_topic_detail":"<one sentence>",
 "position_stated": true|false,
 "position":"<the student's position in <=12 words>",
 "contribution_ok": true|false,
 "contribution_detail":"<is the idea NEW, or a repeat of a classmate or the prompt?>",
 "engages_classmates":["<name>"],
 "engagement_quality":"strong"|"partial"|"none",
 "has_example": true|false,
 "example_detail":"<what the example is, or why it is missing>",
 "has_mechanism": true|false,
 "mechanism_detail":"<does the student explain HOW the example proves the claim?>",
 "summary":"<one sentence on task completion>"}"""
    else:
        job = """Judge how the spoken answer functions as an interview response.
Return JSON:
{"on_topic": true|false,
 "on_topic_detail":"<one sentence>",
 "forced_choice": true|false,
 "forced_choice_answered": true|false,
 "forced_choice_detail":"<if the question asked the student to choose, did sentence 1 choose?>",
 "elaboration_ok": true|false,
 "elaboration_detail":"<is there a concrete example with a number, name, time or action?>",
 "complete_ending": true|false,
 "ending_detail":"<does the answer finish its last sentence?>",
 "strong_phrase_ok": true|false,
 "strong_phrase_detail":"<name any strong phrase or idiom used>",
 "summary":"<one sentence on task completion>"}"""
    return [
        {"role": "system", "content": RATER_SYS},
        {"role": "user", "content":
         f"{_criteria(task)}\n\nTASK TYPE: {TASK_LABEL[task]}\n\n"
         f"{_context_block(task, payload)}\n\n{job}"},
    ]


_ERR_SCHEMA = """Return JSON:
{"errors":[{"original":"<exact text copied from the student's response>",
            "problem":"<the error type in 2-5 words>",
            "correction":"<the corrected text>",
            "rule":"<the underlying rule in one short sentence>",
            "severity":"high"|"medium"|"low"}]}
Rules:
- "original" MUST be copied verbatim from the student's response. Never invent text.
- Quote the SHORTEST span that contains the error - normally 2 to 8 words.
  Never quote a whole sentence when a phrase is enough.
  GOOD: "prices plays" -> "prices play"
  BAD:  "however he overlooked the fact that some factors like lower prices plays more significant roles"
- "correction" must be the same span, fixed - not a rewritten sentence.
- One error per item. If a sentence has three errors, that is three items.
- Report every real instance, but never invent errors. If there are none, return {"errors":[]}.
- Maximum 12 items. Order by severity, highest first."""


def p_errors_grammar(task: str, payload: dict, stats: dict) -> list[dict]:
    focus = """Look ONLY for GRAMMAR errors. Check these in order:
1. Subject-verb agreement (find the head noun, ignore intervening phrases)
2. Articles (a / an / the / zero) and countability (feedback, research, information, advice are uncountable)
3. Verb patterns: suggest/recommend + -ing or that (never "to"); ability to + base verb; affect takes no preposition
4. Prepositions after verbs and adjectives
5. Conditionals: "if you could / were to" requires "would"
6. Double conjunctions: "although ... but", "because ... so"
7. Possessives and its/it's
8. Pronoun case, resumptive pronouns ("the book that I read it"), unclear reference
9. Tense consistency
10. Word order and embedded questions ("how can I" inside a clause should be "how I can")
11. Comparatives ("more easier", "way too harder")"""
    return [
        {"role": "system", "content": RATER_SYS},
        {"role": "user", "content":
         f"{_context_block(task, payload)}\n\n{_stats_block(stats)}\n\n"
         f"{focus}\n\n{_ERR_SCHEMA}"},
    ]


def p_errors_vocab(task: str, payload: dict, stats: dict) -> list[dict]:
    register = ("Spoken register: flag anything too formal or bookish for an interview "
                "(e.g. 'I concur', 'I endorse', 'pivotal')."
                if task == "speaking" else
                "Register: flag anything too formal for the recipient, or too casual "
                "for an official one.")
    focus = f"""Look ONLY for VOCABULARY, COLLOCATION and REGISTER problems. Check:
1. Collocations that are grammatical but not English - usually literal translations
   (e.g. "personal works" -> "personal projects", "make their ROIs more" -> "increase their profits")
2. Vague placeholder nouns ("a lot of things", "this situation", "a good sample")
3. Absolute / overstated claims that should be hedged
   ("This clearly demonstrates" -> "This example suggests"; "he healed" -> "his anxiety improved")
4. Word choice that does not fit the context
5. Repetition of the same word or phrase
6. {register}
Do NOT report spelling or grammar here - only word choice and phrasing."""
    return [
        {"role": "system", "content": RATER_SYS},
        {"role": "user", "content":
         f"{_context_block(task, payload)}\n\n{_stats_block(stats)}\n\n"
         f"{focus}\n\n{_ERR_SCHEMA}"},
    ]


def p_errors_mechanics(task: str, payload: dict, stats: dict) -> list[dict]:
    if task == "speaking":
        focus = """This is a SPOKEN transcript, so ignore spelling and punctuation.
Look ONLY for DELIVERY problems visible in the transcript:
1. False starts and self-repairs ("I totally I agree", "creating, creating music")
2. Filler words and hesitation markers
3. Repeated words or restarted clauses
4. Run-on chains linked by "and"
5. Sentences that trail off unfinished
For each, "correction" is the clean spoken version."""
    else:
        focus = """Look ONLY for MECHANICS errors:
1. Spelling (the measured facts already list some - include them and add any others)
2. Capitalisation (days, months, nationalities, brand names, sentence starts, after a comma)
3. Punctuation: missing comma after However/Moreover/Unfortunately; comma splices;
   semicolon before a coordinating conjunction; spacing around full stops
4. Formatting (missing paragraph breaks, missing greeting or sign-off)"""
    return [
        {"role": "system", "content": RATER_SYS},
        {"role": "user", "content":
         f"{_context_block(task, payload)}\n\n{_stats_block(stats)}\n\n"
         f"{focus}\n\n{_ERR_SCHEMA}"},
    ]


def p_subscores(task: str, payload: dict, stats: dict, task_check: dict,
                errors: dict) -> list[dict]:
    dims = SUBSCORES[task]
    counts = {k: len(v) for k, v in errors.items()}
    schema = ("{\"subscores\":[" +
              ",".join(f'{{"dimension":"{d}","score":<0-5, halves allowed>,'
                       f'"comment":"<one sentence of evidence>"}}' for d in dims) +
              "]}")
    return [
        {"role": "system", "content": RATER_SYS},
        {"role": "user", "content":
         f"{_criteria(task)}\n\n{BAND_GUIDE}\n\n"
         f"{_context_block(task, payload)}\n\n{_stats_block(stats)}\n\n"
         f"TASK-COMPLETION ANALYSIS:\n{json.dumps(task_check, ensure_ascii=False)}\n\n"
         f"ERROR COUNTS FOUND BY THE ANALYSIS STAGES: {json.dumps(counts)}\n\n"
         f"Give a sub-score from 0 to 5 for each dimension below, using the band "
         f"guide strictly. Frequent language errors must pull Grammar, Vocabulary "
         f"and Mechanics down to 2.5-3 even when the ideas are strong.\n"
         f"Dimensions: {dims}\n\nReturn JSON exactly:\n{schema}"},
    ]


def p_verdict(task: str, payload: dict, stats: dict, task_check: dict,
              errors: dict, subscores: list) -> list[dict]:
    return [
        {"role": "system", "content": RATER_SYS},
        {"role": "user", "content":
         f"{BAND_GUIDE}\n\nTASK: {TASK_LABEL[task]}\n\n"
         f"{_context_block(task, payload)}\n\n{_stats_block(stats)}\n\n"
         f"TASK COMPLETION:\n{json.dumps(task_check, ensure_ascii=False)}\n\n"
         f"SUB-SCORES:\n{json.dumps(subscores, ensure_ascii=False)}\n\n"
         f"ERROR COUNTS: {json.dumps({k: len(v) for k, v in errors.items()})}\n\n"
         "Give the final verdict. Be strict: a response with relevant ideas but "
         "frequent grammar/collocation/mechanics errors is a 3, not a 4.\n"
         "Return JSON:\n"
         '{"score": <0-5, halves allowed>,'
         ' "justification":"<one sentence tying the score to the rubric>",'
         ' "main_limiter":"<the single biggest thing holding the score down, <=12 words>",'
         ' "strengths":["<3 short bullets>"],'
         ' "upgrade_plan":["<exactly 3 specific, actionable steps based on THIS response>"]}'},
    ]


# ───────────────────── MODEL-ANSWER pipeline ─────────────────────

def p_extract_ideas(task: str, payload: dict) -> list[dict]:
    return [
        {"role": "system", "content": COACH_SYS},
        {"role": "user", "content":
         f"{_context_block(task, payload)}\n\n"
         "Extract the student's OWN ideas, arguments and examples - the content, "
         "not the wording. Ignore all language errors; recover the intended meaning.\n"
         "Return JSON:\n"
         '{"position":"<the student\'s stance in <=15 words>",'
         ' "main_ideas":["<each distinct idea, in clean English>"],'
         ' "examples":["<each concrete example the student used>"],'
         ' "engagement":["<how they responded to classmates, if at all>"]}'},
    ]


_TEMPLATES = {
    "discussion": """Use this proven 8-sentence structure:
S1 Position: "I agree with <Student> that <their point restated>."  (never "I concur")
S2 Contribution: "I would add that <student's own idea> is often one of the most important factors here."
S3 Explanation: "This matters because <one clause only>."
S4 Example: "For example, <concrete case>."
S5 Mechanism: "As a result, <step 1> leads to <step 2>, which <effect>."
S6 Concession: "<Other student> makes a fair point about <their topic>."
S7 Rebuttal (SEPARATE sentence): "However, <counter-reason> can matter more in practice, because <reason>."
S8 Close: "For this reason, I believe <position>."  (never "Therefore, although X, but Y")
Target 135-150 words, exactly 8 sentences.""",
    "email": """Use this structure:
1 Greeting matched to the recipient (Dear Mr./Ms. X for officials, Hi <name> for friends)
2 Purpose in the first line
3 Context: 2-3 sentences with one concrete detail
4 EVERY bullet from the task prompt, each explicitly - if a bullet says "ask", include a question mark
5 Request phrased with "Could you please...?" or "Would it be possible to...?"
6 One polite closing line + sign-off
Target 110-130 words, 8-9 sentences.""",
    "speaking": """Use the 45-second interview frame:
1 Direct answer (5-7s) - if the question is a forced choice, the choice is IN SENTENCE ONE, in the question's own words
2 Main reason (8-10s) - "The main reason is that..."
3 Example (15-18s) - concrete, with a number, name, time or specific action
4 Conclusion (5-7s) - a COMPLETE final sentence, never trailing off
Target 115-140 words. Natural spoken English, contractions welcome, no bookish words.""",
}


def p_outline(task: str, payload: dict, ideas: dict) -> list[dict]:
    return [
        {"role": "system", "content": COACH_SYS},
        {"role": "user", "content":
         f"{_context_block(task, payload)}\n\n"
         f"THE STUDENT'S OWN IDEAS (you must build on these, not replace them):\n"
         f"{json.dumps(ideas, ensure_ascii=False, indent=1)}\n\n"
         f"{_TEMPLATES[task]}\n\n"
         "Plan a 5/5 answer that keeps the student's ideas and examples. "
         "Where an example is vague, make it concrete but keep its subject.\n"
         "Return JSON:\n"
         '{"plan":[{"slot":"<S1 / Greeting / Direct answer ...>",'
         '"content":"<what this sentence will say, in plain English>"}]}'},
    ]


def p_model_answer(task: str, payload: dict, ideas: dict, outline: dict) -> list[dict]:
    return [
        {"role": "system", "content":
         "You are an expert TOEFL tutor writing a model answer. Reply with valid "
         "JSON only - no prose, no markdown fences."},
        {"role": "user", "content":
         f"{_context_block(task, payload)}\n\n"
         f"STUDENT'S OWN IDEAS (must be preserved):\n"
         f"{json.dumps(ideas, ensure_ascii=False)}\n\n"
         f"APPROVED PLAN:\n{json.dumps(outline, ensure_ascii=False, indent=1)}\n\n"
         f"{_TEMPLATES[task]}\n\n"
         "Write the full-score (5/5) answer now, following the plan sentence by "
         "sentence. Requirements:\n"
         "- Keep the student's ideas and examples; this must read as THEIR answer, improved.\n"
         "- NEVER invent statistics, percentages, dates, study results or company "
         "figures. A TOEFL answer needs concrete DETAIL, not fabricated data. "
         "Write 'unusually low prices', not 'prices 20% lower'.\n"
         "- Simple, accurate, idiomatic English. No rare words. No memorised-sounding phrases.\n"
         "- Hedge every claim (often, may, many, can, in practice).\n"
         "- Zero grammar, collocation or spelling errors.\n"
         "- Realistic for a timed test - do not over-write.\n"
         'Return JSON:\n{"answer":"<the complete answer as plain text, with \\n for line breaks>"}'},
    ]


def p_corrected(task: str, payload: dict, errors: dict) -> list[dict]:
    flat = [e for lst in errors.values() for e in lst][:24]
    return [
        {"role": "system", "content":
         "You are a TOEFL tutor producing a minimally-corrected version. Reply "
         "with valid JSON only."},
        {"role": "user", "content":
         f"{_context_block(task, payload)}\n\n"
         f"ERRORS FOUND:\n{json.dumps(flat, ensure_ascii=False)}\n\n"
         "Rewrite the student's response applying ONLY these corrections plus any "
         "other clear language errors. Preserve the student's ideas, structure, "
         "order and length. Do not add new content or new examples. This is a "
         "corrected version, not an improved one.\n"
         'Return JSON:\n{"corrected":"<the corrected text, \\n for line breaks>"}'},
    ]


def p_verify(task: str, payload: dict, answer: str, stats_note: str) -> list[dict]:
    return [
        {"role": "system", "content": RATER_SYS},
        {"role": "user", "content":
         f"TASK: {TASK_LABEL[task]}\n\nTASK PROMPT:\n{payload['question']}\n\n"
         f"CANDIDATE 5/5 ANSWER:\n{answer}\n\n{stats_note}\n\n"
         "Check this answer as a strict rater. If anything is wrong, fix it and "
         "return the corrected full text.\n"
         "Check: every task requirement covered; zero grammar/collocation/spelling "
         "errors; no 'although...but'; claims hedged; correct length; natural tone; "
         "and NO invented statistics, percentages or study results - if you find "
         "any, replace them with a qualitative description.\n"
         "Return JSON:\n"
         '{"issues":["<any problems found, or empty list>"],'
         ' "final_answer":"<the final text, corrected if needed>"}'},
    ]


def p_speaking_chunks(answer: str) -> list[dict]:
    return [
        {"role": "system", "content": COACH_SYS},
        {"role": "user", "content":
         f"MODEL SPOKEN ANSWER:\n{answer}\n\n"
         "Prepare this for delivery practice. Split it into thought groups of "
         "3-7 words separated by ' / ', and choose 3-5 content words to stress.\n"
         "Return JSON:\n"
         '{"chunked":"<the answer with / between thought groups>",'
         ' "stress_words":["<3-5 words, UPPERCASE>"],'
         ' "delivery_notes":["<2-4 short, specific tips>"]}'},
    ]


# ─────────────────────── LESSON pipeline ───────────────────────

CATEGORY_TITLES = {
    "grammar": "Grammar",
    "vocabulary": "Vocabulary & collocation",
    "mechanics": "Mechanics",
    "delivery": "Delivery",
    "structure": "Task & structure",
}


def p_lesson(category: str, errors: list, task: str, extra_context: str = "") -> list[dict]:
    return [
        {"role": "system", "content": COACH_SYS},
        {"role": "user", "content":
         f"TASK TYPE: {TASK_LABEL[task]}\nCATEGORY: {CATEGORY_TITLES.get(category, category)}\n\n"
         f"ERRORS THE STUDENT ACTUALLY MADE:\n"
         f"{json.dumps(errors, ensure_ascii=False, indent=1)}\n{extra_context}\n\n"
         "Write a SHORT, dense lesson that fixes the underlying causes - not a list "
         "of individual corrections. Group the errors into at most 4 patterns. "
         "For each pattern give the rule, why a Persian speaker gets it wrong, and "
         "the student's own examples.\n"
         "IMPORTANT:\n"
         "- Only describe patterns that are actually present in the errors above. "
         "Do not teach a rule the student did not break.\n"
         "- Put each example under the pattern it actually belongs to. An example "
         "must illustrate its own pattern.\n"
         "- Teach standard American English usage.\n"
         "Return JSON:\n"
         '{"headline":"<one sentence naming the single biggest pattern>",'
         ' "patterns":[{"name":"<short pattern name>",'
         '  "rule":"<the rule in 1-2 sentences>",'
         '  "root_cause":"<why a Farsi speaker makes this error, 1-2 sentences>",'
         '  "your_examples":[{"wrong":"<their text>","right":"<the fix>"}],'
         '  "quick_test":"<a 1-sentence self-check they can run while proofreading>"}],'
         ' "memorise":["<3-6 fixed phrases or forms to over-learn>"]}'},
    ]


def p_drills(category: str, lesson: dict, errors: list, task: str) -> list[dict]:
    return [
        {"role": "system", "content": COACH_SYS},
        {"role": "user", "content":
         f"CATEGORY: {CATEGORY_TITLES.get(category, category)}\nTASK: {TASK_LABEL[task]}\n\n"
         f"THE LESSON JUST TAUGHT:\n{json.dumps(lesson, ensure_ascii=False)}\n\n"
         f"THE STUDENT'S ORIGINAL ERRORS:\n{json.dumps(errors, ensure_ascii=False)}\n\n"
         "Write practice exercises that make these patterns automatic.\n"
         "Rules:\n"
         "- 8 to 12 items, all DIFFERENT from each other, ordered easy to hard.\n"
         "- At least 3 items must be built from the student's OWN sentences.\n"
         "- Every item must require the student to CHANGE something. The prompt "
         "must contain the error, and the answer must be the corrected form. "
         "Never write a prompt that is already correct.\n"
         "  GOOD: prompt 'Lower prices plays a key role.' answer 'Lower prices play a key role.'\n"
         "  BAD:  prompt 'I suggest that you rest.'        answer 'I suggest that you rest.'\n"
         "- Only teach the patterns in the lesson above. Do not introduce unrelated rules.\n"
         "- Each item must be answerable in under 20 seconds.\n"
         "- Give the answer AND a one-line reason for every item.\n"
         "Return JSON:\n"
         '{"instructions":"<one sentence telling the student what to do>",'
         ' "items":[{"n":1,"prompt":"<the exercise sentence or question>",'
         '           "answer":"<the correct answer>","why":"<one short line>"}],'
         ' "spoken_drill":"<one drill they should do ALOUD, 1-2 sentences>"}'},
    ]


def p_study_plan(task: str, verdict: dict, lessons: dict) -> list[dict]:
    return [
        {"role": "system", "content": COACH_SYS},
        {"role": "user", "content":
         f"TASK: {TASK_LABEL[task]}\n"
         f"VERDICT:\n{json.dumps(verdict, ensure_ascii=False)}\n\n"
         f"LESSON HEADLINES:\n"
         f"{json.dumps({k: v.get('headline') for k, v in lessons.items()}, ensure_ascii=False)}\n\n"
         "Write a focused 7-day study plan that would move this student up one band "
         "on this task. Be concrete: name the pattern, the drill, and the minutes.\n"
         "Return JSON:\n"
         '{"days":[{"day":1,"focus":"<short>","tasks":["<2-3 concrete actions with minutes>"]}],'
         ' "single_highest_value_habit":"<one sentence>"}'},
    ]


def p_expand(task: str, payload: dict, answer: str, have: int, need: int) -> list[dict]:
    """The answer came in under the ETS minimum: lengthen it without padding."""
    return [
        {"role": "system", "content":
         "You are a TOEFL tutor. Reply with valid JSON only."},
        {"role": "user", "content":
         f"TASK: {TASK_LABEL[task]}\n\nTASK PROMPT:\n{payload['question']}\n\n"
         f"CURRENT ANSWER ({have} words):\n{answer}\n\n"
         f"This is below the ETS minimum. It must be at least {need} words.\n"
         "Expand it to that length by developing the EXAMPLE and the causal chain: "
         "add a concrete circumstance, or one more step showing HOW the example "
         "proves the claim.\n"
         "HARD RULES:\n"
         "- Keep every existing sentence, in the same order, with the same meaning. "
         "Only add to them. Never rewrite the opening or change the position.\n"
         "- NEVER invent statistics, percentages, dates or study results. "
         "Say 'unusually low prices', not 'prices 20\% lower'. Made-up numbers are "
         "a serious error, not a concrete detail.\n"
         "- Do NOT add a new argument and do NOT repeat yourself.\n"
         'Return JSON:\n{"answer":"<the expanded answer>"}'},
    ]
