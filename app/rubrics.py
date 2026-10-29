"""Official ETS 2026 scoring dimensions and self-grading checklists.

Source: ETS TOEFL Technical Manual 2026 / TOEFL iBT Writing & Speaking
Scoring Guides, as reproduced in the 2026 self-grading rubric document.
The 2026 format: Speaking = Listen and Repeat + Take an Interview;
Writing = Build a Sentence + Write an Email + Write for an Academic Discussion.
"""

WRITING_CRITERIA = """OFFICIAL ETS 2026 TOEFL WRITING GRADING CRITERIA
Content
  - Number of Sentences ....... too many short sentences is penalised
  - Discourse Coherence ....... transitional words and phrases required
  - Similarity to Prompt ...... every prompt bullet must be addressed
Vocabulary and Grammar
  - Sentence Variety .......... too many simple sentences is penalised
  - Word Frequency ............ varied vocabulary expected
  - Correctness of Collocations  phrases must not be omitted or used awkwardly
Social Conventions (EMAIL ONLY)
  - Politeness Indicators ..... modals and hedge words must be present and correct
Accuracy
  - Grammaticality ............ no awkward or inappropriate grammar
  - Grammatical Errors ........ few incorrect structures
  - Word or Usage Errors ...... no words/phrases that do not fit the context
  - Mechanical Errors ......... few typos, misspellings, formatting errors"""

SPEAKING_CRITERIA = """OFFICIAL ETS 2026 TOEFL SPEAKING GRADING CRITERIA (Take an Interview)
Fluency
  - Speaking rate, length of uninterrupted runs, number of pauses, number of hesitations
Intelligibility
  - Correctness of pronunciation, naturalness of speech rhythm, naturalness of prosody
Language Use: Vocabulary and Grammar
  - Vocabulary diversity, vocabulary richness, grammaticality, grammatical accuracy
Organization
  - Discourse coherence (clear beginning, middle, end), use of discourse connectives"""

BAND_GUIDE = """SCORE BANDS (0-5), applied strictly as a real ETS rater would:
5 - Fully accomplishes the task. Well developed and coherent. Effective, precise
    and idiomatic language. At most a few minor slips that never obscure meaning.
4 - Accomplishes the task with mostly effective language. Some lexical or
    grammatical imprecision, but meaning is consistently clear.
3 - Partially successful. Ideas relevant but development or language control is
    inconsistent. Noticeable grammar, collocation or mechanics errors that
    require the reader to work. THIS IS THE DEFAULT FOR A RESPONSE WITH GOOD
    IDEAS BUT FREQUENT LANGUAGE ERRORS.
2 - Limited. Task only partly addressed, or errors frequent enough to obscure meaning.
1 - Minimal relevant content or largely incomprehensible language.
0 - Blank, off-topic, not in English, or copied from the prompt."""

EMAIL_CHECKLIST = [
    ("min_words", "At least 100 words"),
    ("max_sentences", "11 sentences or fewer"),
    ("transitions", "At least one transitional word or phrase"),
    ("bullets", "All three prompt bullets addressed"),
    ("multi_clause", "At least two sentences with more than one clause"),
    ("coord_subord", "One coordinating AND one subordinating conjunction"),
    ("advanced_vocab", "At least two advanced vocabulary items"),
    ("greeting_closing", "Polite opening and closing statement"),
    ("hedge", "Uses 'could', 'would' or a hedge word at least once"),
    ("typos", "Fewer than four typos / spelling / formatting mistakes"),
    ("grammar_errors", "Fewer than two grammatical mistakes"),
]

DISCUSSION_CHECKLIST = [
    ("min_words", "At least 120 words"),
    ("max_sentences", "12 sentences or fewer"),
    ("transitions", "At least one transitional word or phrase"),
    ("on_topic", "Addresses the prompt and stays on topic"),
    ("contribution", "Relevant opinion + supporting reason + appropriate example"),
    ("multi_clause", "At least two sentences with more than one clause"),
    ("coord_subord", "One coordinating AND one subordinating conjunction"),
    ("advanced_vocab", "At least two advanced vocabulary items"),
    ("typos", "Fewer than four typos / spelling / formatting mistakes"),
    ("grammar_errors", "Fewer than two grammatical mistakes"),
]

SPEAKING_CHECKLIST = [
    ("fillers", "Fewer than three fillers (uh, um, you know)"),
    ("on_topic", "Stays on topic and answers the question"),
    ("repeats", "No more than two hesitations or repetitions"),
    ("duration", "Speaks for at least 42 seconds"),
    ("transitions", "At least two transitional words or phrases"),
    ("elaboration", "Elaborates with a developed example, anecdote or explanation"),
    ("min_words", "Response at least 110 words long"),
    ("strong_phrase", "At least one strong phrase, idiom or expression"),
    ("pace", "Natural pace, not too fast or slow (110-125 wpm)"),
    ("clarity", "Clear enough to be easily understood"),
]

SUBSCORES = {
    "email": ["Communicative purpose", "Elaboration", "Organization",
              "Register & social conventions", "Grammar", "Vocabulary", "Mechanics"],
    "discussion": ["Relevance & task completion", "Contribution", "Development & examples",
                   "Organization & coherence", "Grammar & sentence variety",
                   "Vocabulary & collocation", "Mechanics"],
    "speaking": ["Task completion", "Relevance", "Elaboration", "Organization",
                 "Fluency (from transcript)", "Grammar", "Vocabulary & collocation"],
}

TASK_LABEL = {
    "email": "Write an Email",
    "discussion": "Write for an Academic Discussion",
    "speaking": "Take an Interview (Speaking)",
}

TARGETS = {
    "email": {"words": (100, 130), "sentences": (6, 11)},
    "discussion": {"words": (120, 160), "sentences": (7, 12)},
    "speaking": {"words": (110, 145), "sentences": (5, 12)},
}
