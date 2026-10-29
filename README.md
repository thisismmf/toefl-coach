# TOEFL Coach

A local TOEFL iBT **2026-format** correction system. Runs entirely on your own
machine against your own models, and can be pointed at a commercial API whenever
you want a stronger grader.

```bash
./run.sh up        # start + open the browser
./run.sh down      # stop
./run.sh status    # health + available models
./run.sh logs      # follow the log
./run.sh restart
./run.sh reset     # wipe saved runs and charts
```

Default address: <http://127.0.0.1:8781>

---

## What it does

Three **separate** stages, run one at a time. This matters: an 8B local model
collapses when asked to grade, rewrite and teach in a single response, so each
stage is its own run with its own prompt chain.

| Stage | What you get |
|---|---|
| **1 · Score & errors** | ETS-band score, per-dimension sub-scores, grammar / vocabulary / mechanics error tables, task-completion analysis, the official ETS 2026 checklist, and four matplotlib charts |
| **2 · 5/5 answer** | Your own ideas extracted, a minimally-corrected version of your text, and a full-score model answer **built from your ideas** — plus a thought-group delivery script for speaking |
| **3 · Lesson & drills** | For each error category: a short lesson organised by *pattern* (with the Persian-interference root cause), then 8–12 targeted exercises with answers, plus a 7-day study plan |

Stages 2 and 3 both attach to a finished stage-1 run, so they reuse its analysis
instead of re-reading your text from scratch.

### Task types

| Task | Inputs |
|---|---|
| **Write an Email** | task prompt (with bullets) + your email |
| **Academic Discussion** | professor's question + classmate A + classmate B + your post |
| **Take an Interview** | interview question + your transcript + *(optional)* recording length in seconds |

Give the recording length and you also get words-per-minute against the
110–125 wpm target band.

---

## How a single stage is decomposed

Nothing asks the model for more than one kind of thing at a time.

**Score & errors**

```
Python: measure          → words, sentences, clauses, transitions, typos,
                           double conjunctions, comma splices, wpm
LLM 1:  task completion  → bullet coverage / contribution / forced choice
LLM 2:  grammar errors   → JSON array
LLM 3:  vocabulary errors→ JSON array
LLM 4:  mechanics errors → JSON array (merged with the Python typo scan)
LLM 5:  sub-scores       → one score per ETS dimension
LLM 6:  verdict          → final band, limiter, strengths, 3-step plan
Python: charts
```

**5/5 answer** — extract ideas → corrected version → outline → write → verify →
(speaking) chunk into thought groups.

**Lesson & drills** — per category: lesson → drills. Then a study plan. The
assembly into a document happens in Python, never in the model.

Everything countable is counted in Python, not by the model, and handed to it as
established fact. Small models are bad at counting and good at judging.

---

## Choosing a model

The sidebar picks the provider and model live; nothing needs restarting.

- **Ollama (local)** — the model list is read from your running Ollama daemon.
- **Ollama Cloud** — the big hosted models (`gpt-oss:120b`, `gemma4:31b`,
  `nemotron-3`, and others). Needs `OLLAMA_API_KEY`; get one at
  <https://ollama.com/settings/keys>.
- **OpenAI-compatible** — set a base URL and key. Works with OpenAI, OpenRouter,
  Groq, Together, LM Studio, vLLM, llama.cpp's server, and anything else that
  speaks `/v1/chat/completions`.
- **Anthropic** — set a key; uses the Messages API.

Keys live in `.env` (copy `.env.example`), which is gitignored, so you never type
them in the browser. A key typed into the sidebar instead is kept in memory only —
it is never written to `localStorage`.

### About the two Ollama providers

They are not interchangeable. The **local daemon cannot serve cloud models**: it
lists `gpt-oss:120b-cloud` but returns an error when you actually call it. Cloud
models go through **Ollama Cloud**, which talks to `ollama.com` directly and
drops the `-cloud` suffix for you. If you pick a `-cloud` model under the local
provider, the app says so and offers to switch.

Also note that the free Ollama tier does not cover every model the cloud lists.
At the time of writing, this key reaches `gpt-oss:120b`, `gpt-oss:20b`,
`gemma4:31b` and `nemotron-3-nano:30b`; the Kimi, GLM, DeepSeek and Qwen3.5
entries return *"requires a subscription"*. The app reports that as
**"That model is not in your plan"** rather than a generic failure.

### When a model cannot be reached

Every failure to reach a model is caught and classified — no key, rejected key,
model not found, not in your plan, rate limited, or simply unreachable — and the
result page shows what went wrong, what to do about it, and a **dropdown of
models that are reachable right now** with a *Use it & retry* button. The
suggestions are ordered so the ones most likely to work come first, and picking
one re-runs the same stage on the same input.

The **Test** button in the sidebar does the same check on demand, before you
commit to a long run. The badge next to the model label shows *reachable* or
*unreachable*.

### Which model for which stage

The pipeline is built so an 8B model produces usable output, but the three
stages are not equally forgiving. From testing on your own models:

| Stage | Sensitivity | Recommendation |
|---|---|---|
| **1 · Score & errors** | Medium | An 8B model finds real errors reliably, because the counting is done in Python and each error category is asked for separately. `llama3.1:8b` works. |
| **2 · 5/5 answer** | Low | The template and the length guard do most of the work. Any 8B model is fine. |
| **3 · Lesson & drills** | **High** | This is the one that needs a strong model. An 8B will sometimes name a grammar rule that does not match the errors it was given, or invent a rule you did not break. |

A good split on your machine: **Ollama Cloud → `gpt-oss:120b`** for stage 3, and
local `llama3.1:8b` for stages 1 and 2. You change the model in the sidebar
between stages — each stage reads the setting at the moment you launch it.

**A caution about stage 3 on small models.** Treat the lesson as a draft. The
drills are filtered in code (duplicates dropped, and any "exercise" whose prompt
already contains its answer is removed), but a small model can still state a rule
confidently and wrongly. If a rule looks off, it probably is — check it before
you learn it.

---

## Rubrics

Scoring follows the ETS 2026 criteria:

- **Writing** — Content (number of sentences, discourse coherence, similarity to
  prompt), Vocabulary & Grammar (sentence variety, word frequency, correctness of
  collocations), Social Conventions (politeness indicators — email only),
  Accuracy (grammaticality, grammatical errors, word/usage errors, mechanical errors).
- **Speaking, Take an Interview** — Fluency (rate, uninterrupted runs, pauses,
  hesitations), Intelligibility, Language Use (vocabulary diversity and richness,
  grammaticality and accuracy), Organization (coherence, discourse connectives).

The official self-grading checklists are evaluated deterministically where
possible: ≥100 words / ≤11 sentences for email, ≥120 / ≤12 for discussion,
≥110 words and ≥42 seconds for the interview.

---

## Layout

```
app/
  main.py        FastAPI routes; background jobs, UI polls for progress
  config.py      settings and provider defaults
  llm.py         Ollama / OpenAI-compatible / Anthropic + robust JSON extraction
  prompts.py     every prompt in the system, one narrow job each
  pipelines.py   the three stage chains
  textstats.py   deterministic metrics and the ETS checklists
  rubrics.py     ETS 2026 criteria, bands, checklists, target lengths
  charts.py      matplotlib figures
  db.py          SQLite run store
static/          single-page UI (no build step)
data/            SQLite database, generated charts, server log — safe to delete
```

## Notes

- Runs are saved. The sidebar history reopens any past run, including the model
  answer and lesson attached to it.
- Every finished run exports to Markdown with the **Export .md** button, or from
  `GET /api/runs/<id>/export`.
- If the server is restarted while a run is in flight, that run is marked
  interrupted on the next start rather than spinning forever.
- Charts are PNGs under `data/charts/`, served at `/charts/…`.
- The server binds to `127.0.0.1` — it is not reachable from the network. Change
  `TOEFL_HOST` in `.env` if you want that.
- `./run.sh reset` deletes the database and charts; the code is untouched.
# toefl-coach
