"""The three pipelines. Each is a chain of small LLM calls with progress reporting."""
from __future__ import annotations

import asyncio
import difflib
import re
from typing import Any, Callable

from . import charts, db, prompts, textstats
from .llm import chat_json
from .rubrics import SUBSCORES, TARGETS

Progress = Callable[[str, float], None]


def _mk_progress(rid: str) -> Progress:
    def report(stage: str, pct: float) -> None:
        db.update_run(rid, stage=stage, progress=round(pct, 3))
    return report


async def _ask(messages, cfg: dict, **kw) -> Any:
    return await chat_json(
        messages,
        provider=cfg["provider"], model=cfg["model"],
        temperature=cfg.get("temperature", 0.2),
        num_ctx=cfg.get("num_ctx", 8192),
        base_url=cfg.get("base_url") or None,
        api_key=cfg.get("api_key") or None,
        **kw)


_WORDS = re.compile(r"\S+")


def _narrow(original: str, correction: str) -> tuple[str, str]:
    """Shrink a whole-sentence quote down to the span that actually changed.

    Small models habitually quote the entire sentence on both sides. The error
    table is only readable if it shows the offending phrase, so diff the two
    and keep the changed region plus one word of context.
    """
    o, c = original.split(), correction.split()
    if not c:
        return original.strip(), correction.strip()

    # Shape the model often emits for spelling: a whole sentence as "original"
    # and only the fixed word as "correction". Locate the word it meant.
    if len(c) <= 2 and len(o) > 4:
        target = c[0].lower().strip(".,;:!?\"'")
        best, best_r = None, 0.0
        for w in o:
            bare = w.lower().strip(".,;:!?\"'")
            r = difflib.SequenceMatcher(a=bare, b=target).ratio()
            if r > best_r:
                best, best_r = w.strip(".,;:!?\"'"), r
        if best and 0.55 <= best_r < 0.999:
            return best, correction.strip()
        # The "corrected" word is already present and correct: the model
        # produced noise, so signal a drop.
        return "", ""

    if len(o) <= 8:
        return original.strip(), correction.strip()
    sm = difflib.SequenceMatcher(a=[w.lower().strip('.,;:!?"\'') for w in o],
                                 b=[w.lower().strip('.,;:!?"\'') for w in c])
    ops = [op for op in sm.get_opcodes() if op[0] != "equal"]
    if not ops:
        return original.strip(), correction.strip()

    def span(o_lo, o_hi, c_lo, c_hi):
        # One word of context on each side keeps the span intelligible.
        a, b = max(0, o_lo - 1), min(len(o), o_hi + 1)
        x, y = max(0, c_lo - 1), min(len(c), c_hi + 1)
        return " ".join(o[a:b]).strip(), " ".join(c[x:y]).strip()

    span_o, span_c = span(min(op[1] for op in ops), max(op[2] for op in ops),
                          min(op[3] for op in ops), max(op[4] for op in ops))
    if span_o and span_c and len(span_o.split()) <= 12:
        return span_o, span_c

    # Changes are scattered across the sentence: report the largest single one
    # rather than quoting everything back at the student.
    big = max(ops, key=lambda op: (op[2] - op[1]) + (op[4] - op[3]))
    span_o, span_c = span(big[1], big[2], big[3], big[4])
    if not span_o or not span_c or len(span_o.split()) > 12:
        return original.strip(), correction.strip()
    return span_o, span_c


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def _errlist(obj: Any) -> list[dict]:
    """Normalise whatever the model returned into a clean error list."""
    if isinstance(obj, dict):
        obj = obj.get("errors", obj.get("items", []))
    if not isinstance(obj, list):
        return []
    out = []
    for e in obj:
        if not isinstance(e, dict):
            continue
        orig = str(e.get("original") or e.get("phrase") or "").strip()
        corr = str(e.get("correction") or e.get("better") or "").strip()
        if not orig or orig == corr:
            continue
        orig, corr = _narrow(orig, corr)
        if not orig or _key(orig) == _key(corr):
            continue
        sev = str(e.get("severity", "medium")).lower()
        out.append({
            "original": orig,
            "problem": str(e.get("problem") or "").strip() or "language error",
            "correction": corr,
            "rule": str(e.get("rule") or e.get("reason") or "").strip(),
            "severity": sev if sev in ("high", "medium", "low") else "medium",
        })
    return _dedupe(out)[:14]


def _clean_drills(raw: Any) -> list[dict]:
    """Drop the drill items a weak model produces that teach nothing.

    Two failure modes are common: the same exercise emitted several times, and
    an "exercise" whose prompt already contains its own answer.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for it in (raw or []):
        if not isinstance(it, dict):
            continue
        prompt = _text(it.get("prompt"))
        answer = _text(it.get("answer"))
        if not prompt or not answer:
            continue
        kp = _key(prompt)
        if kp in seen:
            continue
        # Nothing to do if the prompt is already the answer.
        if _key(answer) == kp or (len(kp) > 25 and _key(answer) in kp):
            continue
        seen.add(kp)
        out.append({"n": len(out) + 1, "prompt": prompt, "answer": answer,
                    "why": _text(it.get("why"))})
    return out[:12]


def _dedupe(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for e in items:
        k = _key(e["original"])
        if k and k not in seen:
            seen.add(k)
            out.append(e)
    return out


def _dedupe_across(errors: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """The same span must not be reported in two categories."""
    seen: set[str] = set()
    for cat in ("mechanics", "delivery", "grammar", "vocabulary"):
        if cat not in errors:
            continue
        kept = []
        for e in errors[cat]:
            k = _key(e["original"])
            if k in seen:
                continue
            seen.add(k)
            kept.append(e)
        errors[cat] = kept
    return errors


def _text(v: Any, *keys: str) -> str:
    """Coerce whatever the model returned into plain text.

    Models sometimes wrap the answer in another object, return a list of
    paragraphs, or nest it one level deeper than asked. Recover all of those
    rather than failing the run.
    """
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, list):
        return "\n".join(_text(x) for x in v).strip()
    if isinstance(v, dict):
        for k in (*keys, "answer", "final_answer", "corrected", "text",
                  "content", "response", "value"):
            if k in v:
                return _text(v[k])
        # Single-entry wrapper of unknown name.
        if len(v) == 1:
            return _text(next(iter(v.values())))
        return "\n".join(f"{k}: {_text(x)}" for k, x in v.items()).strip()
    return str(v).strip()


def _clamp(v: Any, lo: float = 0.0, hi: float = 5.0, default: float = 3.0) -> float:
    try:
        return max(lo, min(hi, round(float(v) * 2) / 2))
    except (TypeError, ValueError):
        return default


# ─────────────────────────── GRADE ───────────────────────────

async def run_grade(rid: str, task: str, payload: dict, cfg: dict) -> dict:
    p = _mk_progress(rid)

    p("Measuring the response", 0.05)
    stats = textstats.analyse(payload["response"], task,
                              payload.get("duration_sec"))

    p("Checking task completion", 0.14)
    task_check = await _ask(prompts.p_task_check(task, payload), cfg)

    p("Finding grammar errors", 0.30)
    grammar = _errlist(await _ask(prompts.p_errors_grammar(task, payload, stats), cfg))

    p("Finding vocabulary & collocation errors", 0.46)
    vocab = _errlist(await _ask(prompts.p_errors_vocab(task, payload, stats), cfg))

    key3 = "delivery" if task == "speaking" else "mechanics"
    p(f"Finding {key3} errors", 0.60)
    third = _errlist(await _ask(prompts.p_errors_mechanics(task, payload, stats), cfg))

    # Fold in typos the analyser found that the model missed.
    if task != "speaking":
        have = {e["original"].lower() for e in third}
        for t in stats["likely_typos"]:
            if t["original"].lower() not in have:
                third.append({"original": t["original"], "problem": "Spelling",
                              "correction": t["suggestion"],
                              "rule": "Correct spelling.", "severity": "high"})

    errors = _dedupe_across({"grammar": grammar, "vocabulary": vocab, key3: third})

    p("Scoring against the ETS rubric", 0.74)
    raw_sub = await _ask(prompts.p_subscores(task, payload, stats, task_check, errors), cfg)
    got = raw_sub.get("subscores", []) if isinstance(raw_sub, dict) else raw_sub
    by_dim = {str(s.get("dimension", "")).lower(): s
              for s in got if isinstance(s, dict)}
    subscores = []
    for dim in SUBSCORES[task]:
        s = by_dim.get(dim.lower(), {})
        subscores.append({"dimension": dim,
                          "score": _clamp(s.get("score")),
                          "comment": str(s.get("comment", "")).strip()})

    p("Writing the verdict", 0.86)
    verdict = await _ask(
        prompts.p_verdict(task, payload, stats, task_check, errors, subscores), cfg)
    verdict = verdict if isinstance(verdict, dict) else {}
    verdict["score"] = _clamp(verdict.get("score"))
    verdict.setdefault("justification", "")
    verdict.setdefault("main_limiter", "")
    verdict["strengths"] = [str(x) for x in (verdict.get("strengths") or [])][:4]
    verdict["upgrade_plan"] = [str(x) for x in (verdict.get("upgrade_plan") or [])][:3]

    extra = {
        "bullets_ok": task_check.get("bullets_ok"),
        "bullets_detail": "; ".join(
            f"{b.get('bullet', '')[:44]}: {'yes' if b.get('addressed') else 'NO'}"
            for b in task_check.get("bullets", [])) if task == "email" else "",
        "on_topic": task_check.get("on_topic"),
        "on_topic_detail": task_check.get("on_topic_detail", ""),
        "contribution_ok": task_check.get("contribution_ok"),
        "contribution_detail": task_check.get("contribution_detail", ""),
        "elaboration_ok": task_check.get("elaboration_ok"),
        "elaboration_detail": task_check.get("elaboration_detail", ""),
        "strong_phrase_ok": task_check.get("strong_phrase_ok"),
        "strong_phrase_detail": task_check.get("strong_phrase_detail", ""),
    }
    checks = textstats.checklist(stats, task, extra)

    result = {"stats": stats, "task_check": task_check, "errors": errors,
              "subscores": subscores, "verdict": verdict, "checklist": checks,
              "target": TARGETS[task]}

    p("Drawing charts", 0.94)
    result["charts"] = await asyncio.to_thread(charts.build_all, rid, task, result)

    p("Done", 1.0)
    return result


# ───────────────────────── MODEL ANSWER ─────────────────────────

async def run_model_answer(rid: str, task: str, payload: dict, cfg: dict,
                           grade: dict | None) -> dict:
    p = _mk_progress(rid)
    out: dict[str, Any] = {}

    p("Extracting your own ideas", 0.10)
    ideas = await _ask(prompts.p_extract_ideas(task, payload), cfg)
    ideas = ideas if isinstance(ideas, dict) else {}
    out["ideas"] = {
        "position": _text(ideas.get("position")),
        "main_ideas": [_text(x) for x in (ideas.get("main_ideas") or [])],
        "examples": [_text(x) for x in (ideas.get("examples") or [])],
        "engagement": [_text(x) for x in (ideas.get("engagement") or [])],
    }
    ideas = out["ideas"]

    if grade and grade.get("errors"):
        p("Building the corrected version", 0.28)
        c = await _ask(prompts.p_corrected(task, payload, grade["errors"]), cfg)
        out["corrected"] = _text(c, "corrected")
        out["corrected_stats"] = textstats.analyse(out["corrected"], task) \
            if out["corrected"] else None

    p("Planning the 5/5 answer", 0.46)
    outline = await _ask(prompts.p_outline(task, payload, ideas), cfg)
    plan = (outline or {}).get("plan") if isinstance(outline, dict) else outline
    plan = [{"slot": _text(p.get("slot")) or f"Step {i}",
             "content": _text(p.get("content"))}
            for i, p in enumerate(plan or [], 1) if isinstance(p, dict)]
    outline = {"plan": plan}
    out["outline"] = outline

    p("Writing the 5/5 answer", 0.66)
    draft = await _ask(prompts.p_model_answer(task, payload, ideas, outline), cfg)
    answer = _text(draft, "answer")

    p("Verifying against the rubric", 0.82)
    tgt = TARGETS[task]
    note = (f"LENGTH TARGET: {tgt['words'][0]}-{tgt['words'][1]} words, "
            f"{tgt['sentences'][0]}-{tgt['sentences'][1]} sentences.")
    ver = await _ask(prompts.p_verify(task, payload, answer, note), cfg)
    final = _text(ver, "final_answer") or answer
    # A "fix" that loses half the answer is a model failure, not a fix.
    if len(final.split()) < 0.55 * max(len(answer.split()), 1):
        final = answer
    out["model_answer"] = final
    out["verify_issues"] = [str(x) for x in (ver.get("issues") or [])] \
        if isinstance(ver, dict) else []
    if not out["model_answer"]:
        raise RuntimeError("The model returned an empty answer. Try a larger model.")

    # ETS enforces a hard minimum length; a short "perfect" answer cannot score 5.
    need = tgt["words"][0]
    have = len(textstats.words(out["model_answer"]))
    if have < need:
        p("Expanding to the ETS minimum length", 0.88)
        try:
            ex = await _ask(prompts.p_expand(task, payload, out["model_answer"],
                                             have, need), cfg)
            longer = _text(ex, "answer")
            if len(textstats.words(longer)) > have:
                out["model_answer"] = longer
                out["expanded_from"] = have
        except Exception:  # noqa: BLE001
            pass  # keep the shorter answer rather than failing the run

    out["model_stats"] = textstats.analyse(out["model_answer"], task)
    out["length_ok"] = len(textstats.words(out["model_answer"])) >= need

    if task == "speaking":
        p("Preparing the delivery script", 0.92)
        ch = await _ask(prompts.p_speaking_chunks(out["model_answer"]), cfg)
        ch = ch if isinstance(ch, dict) else {}
        out["delivery"] = {
            "chunked": _text(ch.get("chunked")),
            "stress_words": [str(w) for w in (ch.get("stress_words") or [])][:6],
            "delivery_notes": [_text(n) for n in (ch.get("delivery_notes") or [])][:5],
        }

    p("Done", 1.0)
    return out


# ──────────────────────── LESSON & DRILLS ────────────────────────

async def run_lesson(rid: str, task: str, cfg: dict, grade: dict) -> dict:
    p = _mk_progress(rid)
    errors: dict = grade.get("errors", {})
    verdict: dict = grade.get("verdict", {})
    check = grade.get("task_check", {})

    cats = [(k, v) for k, v in errors.items() if v]
    # Task/structure is derived from the completion analysis, not the error lists.
    struct_notes = []
    if task == "email" and check.get("bullets_ok") is False:
        struct_notes.append({"original": "task coverage",
                             "problem": "A prompt bullet was not answered",
                             "correction": check.get("summary", ""),
                             "rule": "Every bullet must be addressed explicitly.",
                             "severity": "high"})
    if task == "discussion":
        if check.get("has_mechanism") is False:
            struct_notes.append({"original": "example without mechanism",
                                 "problem": "Example does not prove the claim",
                                 "correction": check.get("mechanism_detail", ""),
                                 "rule": "Add a causal step between example and conclusion.",
                                 "severity": "high"})
        if check.get("contribution_ok") is False:
            struct_notes.append({"original": "contribution",
                                 "problem": "Idea repeats a classmate or the prompt",
                                 "correction": check.get("contribution_detail", ""),
                                 "rule": "Add an angle neither classmate mentioned.",
                                 "severity": "high"})
    if task == "speaking":
        if check.get("forced_choice") and not check.get("forced_choice_answered"):
            struct_notes.append({"original": "opening sentence",
                                 "problem": "Forced choice not answered",
                                 "correction": check.get("forced_choice_detail", ""),
                                 "rule": "State the choice in sentence 1, in the question's words.",
                                 "severity": "high"})
        if check.get("complete_ending") is False:
            struct_notes.append({"original": "final sentence",
                                 "problem": "Answer trails off",
                                 "correction": check.get("ending_detail", ""),
                                 "rule": "Bank a closing sentence before you start speaking.",
                                 "severity": "high"})
    if struct_notes:
        cats.append(("structure", struct_notes))

    lessons: dict[str, dict] = {}
    drills: dict[str, dict] = {}
    n = max(len(cats), 1)
    for i, (cat, errs) in enumerate(cats):
        base = i / n
        p(f"Lesson: {prompts.CATEGORY_TITLES.get(cat, cat)}", 0.05 + base * 0.85)
        extra = ""
        if cat == "delivery" and grade.get("stats", {}).get("wpm"):
            extra = (f"\nMEASURED PACE: {grade['stats']['wpm']} wpm "
                     f"(natural interview pace is 110-125 wpm).")
        lesson = await _ask(prompts.p_lesson(cat, errs, task, extra), cfg)
        lessons[cat] = lesson if isinstance(lesson, dict) else {}

        p(f"Drills: {prompts.CATEGORY_TITLES.get(cat, cat)}",
          0.05 + (base + 0.5 / n) * 0.85)
        drill = await _ask(prompts.p_drills(cat, lessons[cat], errs, task), cfg)
        d = drill if isinstance(drill, dict) else {}
        d["items"] = _clean_drills(d.get("items"))
        d["instructions"] = _text(d.get("instructions"))
        d["spoken_drill"] = _text(d.get("spoken_drill"))
        drills[cat] = d

    p("Building the study plan", 0.93)
    plan = await _ask(prompts.p_study_plan(task, verdict, lessons), cfg)

    p("Done", 1.0)
    return {"categories": [c for c, _ in cats], "lessons": lessons,
            "drills": drills, "study_plan": plan if isinstance(plan, dict) else {}}
