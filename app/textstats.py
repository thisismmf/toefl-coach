"""Deterministic metrics computed in Python.

Small local models are unreliable at counting. Everything countable is measured
here and handed to the model as established fact, so the model only has to do
what it is good at: judging language.
"""
from __future__ import annotations

import re

TRANSITIONS = [
    "however", "therefore", "moreover", "in addition", "furthermore", "for example",
    "for instance", "as a result", "on the other hand", "on the one hand", "although",
    "even though", "in contrast", "consequently", "besides", "overall", "finally",
    "first", "second", "firstly", "secondly", "in conclusion", "for this reason",
    "that said", "in fact", "instead", "meanwhile", "unfortunately", "in particular",
    "similarly", "nevertheless", "by contrast", "to sum up", "in short",
]
COORDINATING = ["and", "but", "or", "so", "yet", "nor", "for"]
SUBORDINATING = [
    "although", "because", "since", "while", "when", "if", "unless", "whereas",
    "even though", "after", "before", "until", "so that", "whenever", "as long as",
    "though", "in order that", "provided that",
]
FILLERS = ["uh", "um", "erm", "you know", "i mean", "like,", "sort of", "kind of",
           "actually,", "basically", "well,"]
HEDGES = ["could", "would", "might", "may", "perhaps", "possibly", "probably",
          "somewhat", "fairly", "quite", "i think", "i believe", "it seems",
          "often", "usually", "generally", "tend to", "in many cases"]
GREETINGS = ["dear ", "hi ", "hello ", "hey "]
CLOSINGS = ["best regards", "kind regards", "best,", "sincerely", "thanks,",
            "thank you", "regards", "looking forward", "see you", "all the best"]

# Common misspellings this user actually produces, plus general high-frequency ones.
KNOWN_TYPOS = {
    "wheter": "whether", "appereciate": "appreciate", "buisness": "business",
    "buisnesses": "businesses", "ususally": "usually", "outweight": "outweigh",
    "althogh": "although", "althoght": "although", "oppotunities": "opportunities",
    "deciscion": "decision", "technocal": "technical", "possibilty": "possibility",
    "eachother": "each other", "scoial": "social", "paly": "play", "snakcs": "snacks",
    "refards": "regards", "hardd": "hard", "recieve": "receive", "recieved": "received",
    "becuase": "because", "tommorow": "tomorrow", "preapare": "prepare",
    "purchace": "purchase", "aknowledge": "acknowledge", "sipplier": "supplier",
    "recentely": "recently", "enogh": "enough", "devide": "divide", "weekned": "weekend",
    "ilegible": "illegible", "suspention": "suspension", "abcense": "absence",
    "professinal": "professional", "facotr": "factor", "withoud": "without",
    "distroying": "destroying", "intrguing": "intriguing", "comine": "combine",
    "metropolices": "metropolises", "upcomming": "upcoming", "thirdy": "thirty",
    "excelent": "excellent", "studetns": "students", "ragrading": "regarding",
    "perpective": "perspective", "commited": "committed",
    "responibilities": "responsibilities", "restrcitions": "restrictions",
    "raieed": "raised", "surfface": "surface", "exhusted": "exhausted",
    "participaiting": "participating", "sience": "since", "abigious": "ambiguous",
    "underestading": "understanding", "invlolve": "involve", "scincerely": "sincerely",
    "vluable": "valuable", "researchs": "research", "homeworks": "homework",
    "colluges": "colleagues", "seperate": "separate", "definately": "definitely",
    "occured": "occurred", "untill": "until", "beleive": "believe",
    "accomodation": "accommodation", "accomondation": "accommodation",
    "enviroment": "environment", "goverment": "government", "wich": "which",
    "thier": "their", "teh": "the", "alot": "a lot", "infact": "in fact",
}

# Low-frequency / precise items that count as "advanced vocabulary".
ADVANCED_HINTS = [
    "purchasing decision", "operating cost", "office expense", "cognitive",
    "critical thinking", "renewable", "sustainable", "accountability", "incentive",
    "infrastructure", "compelling", "substantial", "considerable", "significant",
    "prioritise", "prioritize", "collaborate", "efficiency", "productivity",
    "perspective", "inevitably", "consequently", "nevertheless", "comprehensive",
    "constructive", "feasible", "detrimental", "beneficial", "supplement",
    "mitigate", "facilitate", "allocate", "reinforce", "undermine", "outweigh",
    "trade-off", "long-term", "short-term", "well-being", "cost-effective",
]

_SENT_SPLIT = re.compile(r"(?<=[.!?])[\s ]+(?=[A-Z\"'(])|\n{2,}")
_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")


def sentences(text: str) -> list[str]:
    body = re.sub(r"\s+", " ", text.strip())
    parts = [p.strip() for p in _SENT_SPLIT.split(body) if p and p.strip()]
    return parts or ([body] if body else [])


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def _strip_email_furniture(text: str) -> str:
    """Drop the greeting line and the sign-off so counts reflect the message."""
    lines = [l for l in text.splitlines()]
    keep = []
    for i, l in enumerate(lines):
        low = l.strip().lower()
        if i < 2 and any(low.startswith(g) for g in GREETINGS):
            continue
        if any(low.startswith(c) for c in CLOSINGS) and i > len(lines) - 4:
            continue
        keep.append(l)
    return "\n".join(keep)


def count_clauses(sentence: str) -> int:
    """Rough finite-clause count: 1 + subordinators + clause-joining coordinators."""
    low = " " + sentence.lower() + " "
    n = 1
    for s in SUBORDINATING:
        n += len(re.findall(rf"\b{re.escape(s)}\b", low))
    for c in ("and", "but", "so", "yet"):
        n += len(re.findall(rf",\s+{c}\b", low))
    n += low.count(";")
    n += len(re.findall(r"\b(which|who|that)\s+\w+", low))
    return n


def find_typos(text: str) -> list[dict]:
    out = []
    seen = set()
    for w in words(text):
        low = w.lower()
        if low in KNOWN_TYPOS and low not in seen:
            seen.add(low)
            out.append({"original": w, "suggestion": KNOWN_TYPOS[low]})
    return out


def normalise(text: str) -> str:
    """Spelling-corrected copy, used only for pattern detection.

    A misspelt keyword must still be seen by the structural checks: without
    this, "Therefore, althogh X, but Y" hides its own double conjunction.
    """
    def sub(m: re.Match) -> str:
        w = m.group(0)
        fix = KNOWN_TYPOS.get(w.lower())
        if not fix:
            return w
        return fix.capitalize() if w[0].isupper() else fix
    return _WORD.sub(sub, text)


def analyse(text: str, task: str, duration_sec: float | None = None) -> dict:
    raw = text.strip()
    body = _strip_email_furniture(raw) if task == "email" else raw
    sents = sentences(body)
    ws = words(body)
    low = normalise(body).lower()

    found_transitions = sorted({t for t in TRANSITIONS
                                if re.search(rf"\b{re.escape(t)}\b", low)})
    found_coord = sorted({c for c in COORDINATING
                          if re.search(rf",\s+{c}\b|\b\w+\s+{c}\s+\w+", low)})
    found_subord = sorted({s for s in SUBORDINATING
                           if re.search(rf"\b{re.escape(s)}\b", low)})
    found_hedges = sorted({h for h in HEDGES if re.search(rf"\b{re.escape(h)}", low)})
    found_advanced = sorted({a for a in ADVANCED_HINTS if a in low})
    found_fillers = [f for f in FILLERS if f in low]
    typos = find_typos(body)  # original spelling, deliberately

    clause_counts = [count_clauses(s) for s in sents]
    multi_clause = sum(1 for c in clause_counts if c >= 2)

    unique_ratio = round(len({w.lower() for w in ws}) / max(len(ws), 1), 3)
    long_sents = [s for s, c in zip(sents, clause_counts) if c >= 4]

    # Sentence-start repetition (a flagged habit in the user's reports).
    starts = [(" ".join(words(s)[:2])).lower() for s in sents if words(s)]
    repeated_starts = sorted({s for s in starts if starts.count(s) > 1 and s})

    stats = {
        "words": len(ws),
        "sentences": len(sents),
        "avg_sentence_len": round(len(ws) / max(len(sents), 1), 1),
        "unique_word_ratio": unique_ratio,
        "multi_clause_sentences": multi_clause,
        "clause_counts": clause_counts,
        "overlong_sentences": long_sents[:4],
        "repeated_sentence_starts": repeated_starts,
        "transitions_found": found_transitions,
        "coordinating_found": found_coord,
        "subordinating_found": found_subord,
        "hedges_found": found_hedges,
        "advanced_vocab_found": found_advanced,
        "fillers_found": found_fillers,
        "likely_typos": typos,
        "has_greeting": any(low.lstrip().startswith(g) for g in GREETINGS)
                        or any(raw.lower().lstrip().startswith(g) for g in GREETINGS),
        "has_closing": any(c in normalise(raw).lower() for c in CLOSINGS),
        "question_marks": raw.count("?"),
        "double_conjunction": bool(
            re.search(r"\balthough\b[^.!?]*\bbut\b", low)
            or re.search(r"\bbecause\b[^.!?]*\bso\b", low)
            or re.search(r"\bdespite\b[^.!?]*\bbut\b", low)),
        "comma_splices": len(re.findall(
            r",\s+(?:I|we|he|she|they|it|this|that|there)\s+\w+ed\b",
            normalise(body))),
    }

    if duration_sec and duration_sec > 0:
        stats["duration_sec"] = round(duration_sec, 1)
        stats["wpm"] = round(len(ws) / (duration_sec / 60.0))
    return stats


def checklist(stats: dict, task: str, extra: dict | None = None) -> list[dict]:
    """Evaluate the official ETS self-grading checklist deterministically.

    `extra` carries the few judgements only the model can make
    (bullet coverage, on-topic, elaboration, clarity).
    """
    extra = extra or {}
    w, s = stats["words"], stats["sentences"]
    typos = len(stats["likely_typos"])
    res: list[tuple[str, str, bool | None, str]] = []

    def add(key, label, ok, detail=""):
        res.append((key, label, ok, detail))

    if task == "email":
        add("min_words", "At least 100 words", w >= 100, f"{w} words")
        add("max_sentences", "11 sentences or fewer", s <= 11, f"{s} sentences")
    elif task == "discussion":
        add("min_words", "At least 120 words", w >= 120, f"{w} words")
        add("max_sentences", "12 sentences or fewer", s <= 12, f"{s} sentences")
    else:
        add("min_words", "At least 110 words", w >= 110, f"{w} words")
        d = stats.get("duration_sec")
        add("duration", "Speaks for at least 42 seconds",
            (d >= 42) if d else None, f"{d}s" if d else "no duration given")
        wpm = stats.get("wpm")
        add("pace", "Natural pace (110-125 wpm)",
            (110 <= wpm <= 135) if wpm else None,
            f"{wpm} wpm" if wpm else "needs duration")
        add("fillers", "Fewer than three fillers",
            len(stats["fillers_found"]) < 3,
            ", ".join(stats["fillers_found"]) or "none detected")

    need_tr = 2 if task == "speaking" else 1
    add("transitions", f"At least {need_tr} transitional word(s)",
        len(stats["transitions_found"]) >= need_tr,
        ", ".join(stats["transitions_found"][:6]) or "none")
    add("multi_clause", "At least two multi-clause sentences",
        stats["multi_clause_sentences"] >= 2,
        f"{stats['multi_clause_sentences']} found")
    add("coord_subord", "One coordinating AND one subordinating conjunction",
        bool(stats["coordinating_found"]) and bool(stats["subordinating_found"]),
        f"coord: {', '.join(stats['coordinating_found'][:3]) or '-'} | "
        f"subord: {', '.join(stats['subordinating_found'][:3]) or '-'}")
    add("advanced_vocab", "At least two advanced vocabulary items",
        len(stats["advanced_vocab_found"]) >= 2 or extra.get("advanced_vocab_ok") is True,
        ", ".join(stats["advanced_vocab_found"][:5]) or "none auto-detected")
    add("typos", "Fewer than four typos", typos < 4,
        ", ".join(t["original"] for t in stats["likely_typos"]) or "none detected")

    if task == "email":
        add("greeting_closing", "Polite opening and closing",
            stats["has_greeting"] and stats["has_closing"],
            f"greeting: {stats['has_greeting']}, closing: {stats['has_closing']}")
        add("hedge", "Uses could / would / a hedge word",
            bool(stats["hedges_found"]), ", ".join(stats["hedges_found"][:5]) or "none")
        add("bullets", "All prompt bullets addressed",
            extra.get("bullets_ok"), extra.get("bullets_detail", ""))
    if task == "discussion":
        add("on_topic", "Addresses the prompt and stays on topic",
            extra.get("on_topic"), extra.get("on_topic_detail", ""))
        add("contribution", "Opinion + reason + example",
            extra.get("contribution_ok"), extra.get("contribution_detail", ""))
    if task == "speaking":
        add("on_topic", "Stays on topic and answers the question",
            extra.get("on_topic"), extra.get("on_topic_detail", ""))
        add("elaboration", "Developed example, anecdote or explanation",
            extra.get("elaboration_ok"), extra.get("elaboration_detail", ""))
        add("strong_phrase", "At least one strong phrase or expression",
            extra.get("strong_phrase_ok"), extra.get("strong_phrase_detail", ""))

    return [{"key": k, "label": l, "pass": p, "detail": d} for k, l, p, d in res]
