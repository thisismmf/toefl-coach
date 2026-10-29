"""Render a finished run as Markdown so it can be saved, printed or pasted."""
from __future__ import annotations

from .prompts import CATEGORY_TITLES
from .rubrics import TASK_LABEL


def _tbl(rows: list[list[str]], head: list[str]) -> str:
    out = ["| " + " | ".join(head) + " |",
           "|" + "|".join(["---"] * len(head)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |")
    return "\n".join(out)


def _errors_md(errors: dict) -> str:
    parts = []
    for cat, lst in (errors or {}).items():
        if not lst:
            continue
        parts.append(f"### {CATEGORY_TITLES.get(cat, cat.title())} ({len(lst)})\n")
        parts.append(_tbl(
            [[e["original"], e["problem"], e["correction"], e["rule"], e["severity"]]
             for e in lst],
            ["You wrote", "Problem", "Correct", "Rule", "Severity"]))
        parts.append("")
    return "\n".join(parts)


def grade_md(run: dict) -> str:
    r = run.get("result") or {}
    v = r.get("verdict") or {}
    st = r.get("stats") or {}
    p = run.get("payload") or {}
    L: list[str] = [
        f"# {TASK_LABEL.get(run['task'], run['task'])} — score {v.get('score')}/5",
        "",
        f"*{run.get('title', '')}*  \n"
        f"Graded by `{run.get('model')}` via `{run.get('provider')}`.",
        "",
        f"> {v.get('justification', '')}",
        "",
        f"**Main limiter:** {v.get('main_limiter', '—')}  ",
        f"**Length:** {st.get('words', 0)} words, {st.get('sentences', 0)} sentences"
        + (f", {st['wpm']} wpm" if st.get("wpm") else ""),
        "",
    ]
    if v.get("strengths"):
        L += ["## What already works", ""] + [f"- {s}" for s in v["strengths"]] + [""]
    if v.get("upgrade_plan"):
        L += ["## 3-step upgrade plan", ""] + \
             [f"{i}. {s}" for i, s in enumerate(v["upgrade_plan"], 1)] + [""]
    if r.get("subscores"):
        L += ["## Rubric sub-scores", "",
              _tbl([[s["dimension"], s["score"], s["comment"]] for s in r["subscores"]],
                   ["Dimension", "Score", "Evidence"]), ""]
    if r.get("errors"):
        L += ["## Errors", "", _errors_md(r["errors"])]
    if r.get("checklist"):
        L += ["## ETS 2026 checklist", "",
              _tbl([["✅" if c["pass"] is True else "❌" if c["pass"] is False else "—",
                     c["label"], c["detail"]] for c in r["checklist"]],
                   ["", "Requirement", "Detail"]), ""]
    L += ["## Your original response", "", "```", p.get("response", ""), "```", ""]
    return "\n".join(L)


def model_md(run: dict) -> str:
    r = run.get("result") or {}
    i = r.get("ideas") or {}
    ms = r.get("model_stats") or {}
    d = r.get("delivery") or {}
    L = [f"# Full-score answer — {TASK_LABEL.get(run['task'], run['task'])}", ""]
    if i.get("position"):
        L += [f"**Your position:** {i['position']}", ""]
    if i.get("main_ideas"):
        L += ["## Your own ideas", ""] + [f"- {x}" for x in i["main_ideas"]] + [""]
    if i.get("examples"):
        L += ["**Your examples**", ""] + [f"- {x}" for x in i["examples"]] + [""]
    if r.get("corrected"):
        L += ["## Corrected version", "",
              "*Your text with the errors fixed and nothing added.*", "",
              r["corrected"], ""]
    L += ["## 5/5 model answer", "",
          f"*{ms.get('words', 0)} words, {ms.get('sentences', 0)} sentences.*", "",
          r.get("model_answer", ""), ""]
    if d.get("chunked"):
        L += ["## Delivery script", "", "```", d["chunked"], "```", ""]
        if d.get("stress_words"):
            L += [f"**Stress:** {', '.join(d['stress_words'])}", ""]
        if d.get("delivery_notes"):
            L += [f"- {n}" for n in d["delivery_notes"]] + [""]
    if (r.get("outline") or {}).get("plan"):
        L += ["## Sentence plan", "",
              _tbl([[s["slot"], s["content"]] for s in r["outline"]["plan"]],
                   ["Slot", "Content"]), ""]
    return "\n".join(L)


def lesson_md(run: dict) -> str:
    r = run.get("result") or {}
    L = [f"# Lesson & drills — {TASK_LABEL.get(run['task'], run['task'])}", ""]
    for cat in r.get("categories", []):
        les = (r.get("lessons") or {}).get(cat) or {}
        dr = (r.get("drills") or {}).get(cat) or {}
        L += [f"## {CATEGORY_TITLES.get(cat, cat.title())}", ""]
        if les.get("headline"):
            L += [f"**{les['headline']}**", ""]
        for pt in les.get("patterns") or []:
            L += [f"### {pt.get('name', '')}", "", pt.get("rule", ""), ""]
            if pt.get("root_cause"):
                L += [f"> **Why you do this:** {pt['root_cause']}", ""]
            ex = pt.get("your_examples") or []
            if ex:
                L += [_tbl([[e.get("wrong", ""), e.get("right", "")] for e in ex],
                           ["You wrote", "Correct"]), ""]
            if pt.get("quick_test"):
                L += [f"*Self-check: {pt['quick_test']}*", ""]
        if les.get("memorise"):
            L += ["**Memorise**", ""] + [f"- {m}" for m in les["memorise"]] + [""]
        if dr.get("items"):
            L += [f"### Drills", "", dr.get("instructions", ""), ""]
            for it in dr["items"]:
                L.append(f"{it['n']}. {it['prompt']}")
            L += ["", "<details><summary>Answers</summary>", ""]
            for it in dr["items"]:
                L.append(f"{it['n']}. **{it['answer']}** — {it['why']}")
            L += ["", "</details>", ""]
        if dr.get("spoken_drill"):
            L += [f"**Say it aloud:** {dr['spoken_drill']}", ""]
    plan = r.get("study_plan") or {}
    if plan.get("days"):
        L += ["## 7-day plan", ""]
        if plan.get("single_highest_value_habit"):
            L += [f"> {plan['single_highest_value_habit']}", ""]
        L += [_tbl([[d.get("day"), d.get("focus"), "<br>".join(d.get("tasks") or [])]
                    for d in plan["days"]], ["Day", "Focus", "Tasks"]), ""]
    return "\n".join(L)


def render(run: dict) -> str:
    return {"grade": grade_md, "model": model_md,
            "lesson": lesson_md}.get(run["kind"], grade_md)(run)
