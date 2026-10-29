"""Matplotlib charts rendered server-side to PNG."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from .config import CHART_DIR  # noqa: E402

BRAND = "#15A38A"
DEEP = "#0C6B5B"
BAD = "#C0392B"
AMBER = "#B7791F"
INK = "#1A1A1A"
SLATE = "#6B7280"
GRID = "#E5EAEE"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.edgecolor": GRID,
    "axes.labelcolor": SLATE,
    "text.color": INK,
    "xtick.color": SLATE,
    "ytick.color": SLATE,
    "figure.dpi": 150,
    "savefig.bbox": "tight",
    "savefig.facecolor": "white",
})


def _colour(v: float) -> str:
    if v >= 4.0:
        return DEEP
    if v >= 3.5:
        return BRAND
    if v >= 3.0:
        return AMBER
    return BAD


def _save(fig, rid: str, name: str) -> str:
    path = CHART_DIR / f"{rid}_{name}.png"
    fig.savefig(path)
    plt.close(fig)
    return f"/charts/{path.name}"


def subscores_chart(rid: str, subscores: list[dict], overall: float) -> str:
    labels = [s["dimension"] for s in subscores][::-1]
    vals = [float(s["score"]) for s in subscores][::-1]
    fig, ax = plt.subplots(figsize=(8.2, 0.52 * len(labels) + 1.4))
    bars = ax.barh(labels, vals, color=[_colour(v) for v in vals], height=0.62)
    for b, v in zip(bars, vals):
        ax.text(v + 0.08, b.get_y() + b.get_height() / 2, f"{v:g}",
                va="center", fontsize=9, fontweight="bold", color=SLATE)
    ax.axvline(overall, color=SLATE, ls="--", lw=1.1, alpha=0.8)
    ax.text(overall, len(labels) - 0.35, f" overall {overall:g}",
            fontsize=8.5, color=SLATE, style="italic")
    ax.set_xlim(0, 5.45)
    ax.set_xticks([0, 1, 2, 3, 4, 5])
    ax.set_xlabel("Score / 5")
    ax.xaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.set_title("Rubric sub-scores", loc="left", fontsize=12,
                 fontweight="bold", color=INK, pad=12)
    return _save(fig, rid, "subscores")


def errors_chart(rid: str, errors: dict) -> str:
    cats, counts, sev = [], [], []
    order = ["grammar", "vocabulary", "mechanics", "delivery"]
    for k in order:
        if k in errors:
            cats.append(k.capitalize())
            counts.append(len(errors[k]))
            sev.append(sum(1 for e in errors[k] if e.get("severity") == "high"))
    if not cats:
        cats, counts, sev = ["None"], [0], [0]
    fig, ax = plt.subplots(figsize=(7.2, 3.5))
    x = range(len(cats))
    ax.bar(x, counts, color=BRAND, width=0.5, label="all errors")
    ax.bar(x, sev, color=BAD, width=0.5, label="high severity")
    for i, (c, s) in enumerate(zip(counts, sev)):
        ax.text(i, c + 0.12, str(c), ha="center", fontsize=10,
                fontweight="bold", color=SLATE)
    ax.set_xticks(list(x))
    ax.set_xticklabels(cats)
    ax.set_ylabel("Errors found")
    ax.set_ylim(0, max(counts + [1]) * 1.25)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    ax.set_title("Where the marks went", loc="left", fontsize=12,
                 fontweight="bold", color=INK, pad=12)
    return _save(fig, rid, "errors")


def checklist_chart(rid: str, checks: list[dict]) -> str:
    labels = [c["label"] for c in checks][::-1]
    states = [c["pass"] for c in checks][::-1]
    colours = [DEEP if s is True else (BAD if s is False else GRID) for s in states]
    fig, ax = plt.subplots(figsize=(8.2, 0.42 * len(labels) + 1.3))
    ax.barh(labels, [1] * len(labels), color=colours, height=0.6)
    for i, s in enumerate(states):
        mark = "PASS" if s is True else ("FAIL" if s is False else "n/a")
        ax.text(0.5, i, mark, ha="center", va="center", fontsize=8.5,
                fontweight="bold",
                color="white" if s is not None else SLATE)
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.tick_params(axis="y", length=0, labelsize=9)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_title("ETS 2026 self-grading checklist", loc="left", fontsize=12,
                 fontweight="bold", color=INK, pad=12)
    return _save(fig, rid, "checklist")


def length_chart(rid: str, stats: dict, target: dict, task: str) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 2.5))
    for ax, key, label in ((axes[0], "words", "Words"),
                           (axes[1], "sentences", "Sentences")):
        lo, hi = target[key]
        val = stats[key]
        top = max(hi * 1.35, val * 1.2)
        ax.add_patch(Rectangle((lo, 0), hi - lo, 1, color=BRAND, alpha=0.16))
        ax.vlines(val, 0, 1.02, color=_colour(4.5 if lo <= val <= hi else 2.5), lw=3.5)
        ax.text(val, 1.12, f"{val}", ha="center", fontsize=11,
                fontweight="bold", color=INK)
        ax.text(lo, -0.26, f"target {lo}-{hi}", ha="left",
                fontsize=8.5, color=SLATE)
        ax.set_xlim(0, top)
        ax.set_ylim(-0.45, 1.5)
        ax.set_yticks([])
        ax.set_title(label, fontsize=10.5, color=INK, fontweight="bold", loc="left")
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
    fig.suptitle("Length against the ETS target band", x=0.02, ha="left",
                 fontsize=12, fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    return _save(fig, rid, "length")


def pace_chart(rid: str, wpm: float) -> str:
    fig, ax = plt.subplots(figsize=(8.2, 1.9))
    ax.add_patch(Rectangle((0, 0), 110, 1, color=BAD, alpha=0.13))
    ax.add_patch(Rectangle((110, 0), 15, 1, color=BRAND, alpha=0.28))
    ax.add_patch(Rectangle((125, 0), 45, 1, color=AMBER, alpha=0.13))
    ax.vlines(wpm, 0, 1.02, color=_colour(4.5 if 110 <= wpm <= 135 else 2.5), lw=4)
    ax.text(wpm, 1.15, f"{wpm:g} wpm", ha="center", fontsize=12,
            fontweight="bold", color=INK)
    ax.text(117.5, -0.3, "target 110-125", ha="center", fontsize=9, color=BRAND)
    ax.text(55, -0.3, "too slow / hesitant", ha="center", fontsize=8.5, color=SLATE)
    ax.text(147, -0.3, "rushed", ha="center", fontsize=8.5, color=SLATE)
    ax.set_xlim(0, 170)
    ax.set_ylim(-0.5, 1.5)
    ax.set_yticks([])
    ax.set_xticks([0, 40, 80, 110, 125, 170])
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.set_title("Speaking pace", loc="left", fontsize=12,
                 fontweight="bold", color=INK, pad=14)
    return _save(fig, rid, "pace")


def build_all(rid: str, task: str, result: dict) -> dict:
    from .rubrics import TARGETS
    out: dict[str, str] = {}
    try:
        if result.get("subscores"):
            out["subscores"] = subscores_chart(
                rid, result["subscores"], float(result["verdict"]["score"]))
        if result.get("errors"):
            out["errors"] = errors_chart(rid, result["errors"])
        if result.get("checklist"):
            out["checklist"] = checklist_chart(rid, result["checklist"])
        if result.get("stats"):
            out["length"] = length_chart(rid, result["stats"], TARGETS[task], task)
            if result["stats"].get("wpm"):
                out["pace"] = pace_chart(rid, result["stats"]["wpm"])
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
    return out
