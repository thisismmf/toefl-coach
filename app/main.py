"""FastAPI server: static UI + run API. Jobs run in the background; the UI polls."""
from __future__ import annotations

import asyncio
import traceback
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, export, llm, pipelines
from .config import CHART_DIR, DEFAULTS, HOST, PORT, PROVIDERS, STATIC_DIR
from .rubrics import TASK_LABEL

app = FastAPI(title="TOEFL Coach", version="1.0.0")
db.init()

Task = Literal["email", "discussion", "speaking"]


class CheckRequest(BaseModel):
    provider: str = DEFAULTS["provider"]
    model: str = DEFAULTS["model"]
    base_url: str | None = None
    api_key: str | None = None


class LLMConfig(BaseModel):
    provider: str = DEFAULTS["provider"]
    model: str = DEFAULTS["model"]
    temperature: float = DEFAULTS["temperature"]
    num_ctx: int = DEFAULTS["num_ctx"]
    base_url: str | None = None
    api_key: str | None = None


class GradeRequest(BaseModel):
    task: Task
    question: str = Field(min_length=5)
    response: str = Field(min_length=5)
    classmate_a: str = ""
    classmate_b: str = ""
    duration_sec: float | None = None
    title: str = ""
    llm: LLMConfig = LLMConfig()


class DerivedRequest(BaseModel):
    grade_id: str
    llm: LLMConfig | None = None


async def _runner(rid: str, coro):
    try:
        result = await coro
        db.update_run(rid, status="done", stage="Done", progress=1.0, result=result)
    except llm.ConnectionProblem as e:
        # A model we could not reach: the UI offers a different one.
        db.update_run(rid, status="error", stage="Cannot reach the model",
                      error=str(e),
                      result={"connection_problem": {"kind": e.kind,
                                                     "hint": e.hint,
                                                     "message": str(e)}})
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        db.update_run(rid, status="error", stage="Failed",
                      error=f"{type(e).__name__}: {e}")


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "defaults": DEFAULTS,
        "providers": [
            {"id": k, "label": v["label"], "has_key": bool(v.get("api_key"))}
            for k, v in PROVIDERS.items()
        ],
    }


@app.get("/api/models")
async def models(provider: str = "ollama", base_url: str = "",
                 api_key: str = "") -> dict:
    got = await llm.list_models(provider, base_url or None, api_key or None)
    cfg = PROVIDERS.get(provider, {})
    return {"provider": provider, "models": got,
            "has_key": bool(api_key or cfg.get("api_key"))}


@app.post("/api/check")
async def check(req: CheckRequest) -> dict:
    """Verify a provider/model actually answers before starting a long run."""
    res = await llm.probe(req.provider, req.model,
                          req.base_url or None, req.api_key or None)
    res["provider"] = req.provider
    res["model"] = req.model
    if not res["ok"]:
        res["alternatives"] = await _alternatives(
            req.provider, res.get("kind", "unreachable"), req.model)
    return res


# Failures that are about one model, not about the provider as a whole.
_MODEL_LEVEL = {"needs_plan", "missing_model", "rate_limited"}


async def _alternatives(failed_provider: str, kind: str = "unreachable",
                        failed_model: str = "") -> list[dict]:
    """Models that could be used instead, so the UI can suggest a swap.

    If only the chosen model is the problem, the same provider's other models
    are the most useful suggestion, so keep them and list them first.
    """
    out: list[dict] = []
    same_ok = kind in _MODEL_LEVEL
    for name, cfg in PROVIDERS.items():
        if name == failed_provider and not same_ok:
            continue
        if name != "ollama" and not cfg.get("api_key"):
            continue  # no credentials configured; not a usable suggestion
        found = [m for m in await llm.list_models(name) if m != failed_model]
        if found:
            entry = {"provider": name, "label": cfg["label"], "models": found[:40]}
            out.insert(0, entry) if name == failed_provider else out.append(entry)
    return out


@app.post("/api/grade")
async def grade(req: GradeRequest) -> dict:
    payload = req.model_dump(exclude={"llm", "title"})
    cfg = req.llm.model_dump()
    title = req.title or f"{TASK_LABEL[req.task]} - {req.question[:48]}"
    rid = db.create_run("grade", req.task, payload, cfg["provider"], cfg["model"], title)
    asyncio.create_task(_runner(rid, pipelines.run_grade(rid, req.task, payload, cfg)))
    return {"id": rid}


def _parent(grade_id: str) -> dict:
    run = db.get_run(grade_id)
    if not run or run["kind"] != "grade":
        raise HTTPException(404, "grade run not found")
    if run["status"] != "done":
        raise HTTPException(409, "that grade run has not finished yet")
    return run


@app.post("/api/model-answer")
async def model_answer(req: DerivedRequest) -> dict:
    parent = _parent(req.grade_id)
    cfg = (req.llm or LLMConfig(provider=parent["provider"],
                                model=parent["model"])).model_dump()
    rid = db.create_run("model", parent["task"], parent["payload"],
                        cfg["provider"], cfg["model"],
                        f"5/5 answer - {parent['title']}", parent_id=parent["id"])
    asyncio.create_task(_runner(rid, pipelines.run_model_answer(
        rid, parent["task"], parent["payload"], cfg, parent["result"])))
    return {"id": rid}


@app.post("/api/lesson")
async def lesson(req: DerivedRequest) -> dict:
    parent = _parent(req.grade_id)
    cfg = (req.llm or LLMConfig(provider=parent["provider"],
                                model=parent["model"])).model_dump()
    rid = db.create_run("lesson", parent["task"], parent["payload"],
                        cfg["provider"], cfg["model"],
                        f"Lesson & drills - {parent['title']}", parent_id=parent["id"])
    asyncio.create_task(_runner(rid, pipelines.run_lesson(
        rid, parent["task"], cfg, parent["result"])))
    return {"id": rid}


@app.get("/api/runs")
async def runs(kind: str = "", limit: int = 60) -> dict:
    return {"runs": db.list_runs(limit, kind or None)}


@app.get("/api/runs/{rid}")
async def run(rid: str) -> Any:
    r = db.get_run(rid)
    if not r:
        raise HTTPException(404, "run not found")
    return r


@app.get("/api/runs/{rid}/children")
async def children(rid: str) -> dict:
    return {"runs": [r for r in db.list_runs(200) if r.get("parent_id") == rid]}


@app.get("/api/runs/{rid}/export")
async def export_run(rid: str) -> Response:
    r = db.get_run(rid)
    if not r:
        raise HTTPException(404, "run not found")
    if r["status"] != "done":
        raise HTTPException(409, "run has not finished")
    md = export.render(r)
    name = f"{r['kind']}-{r['task']}-{rid}.md"
    return Response(md, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.delete("/api/runs/{rid}")
async def delete(rid: str) -> dict:
    db.delete_run(rid)
    return {"ok": True}


app.mount("/charts", StaticFiles(directory=CHART_DIR), name="charts")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.exception_handler(Exception)
async def unhandled(_req, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500,
                        content={"error": f"{type(exc).__name__}: {exc}"})


def main() -> None:
    import uvicorn
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False, log_level="info")


if __name__ == "__main__":
    main()
