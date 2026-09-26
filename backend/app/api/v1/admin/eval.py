from dataclasses import asdict
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from app.api.errors import HistoryDisabledError, NotFoundError
from app.api.schemas import ErrorResponse
from app.api.state import get_services
from app.api.v1.admin.common import ADMIN_ERRORS, History
from app.evaluation.runner import EvalRun, EvalRunner
from app.services import Services

router = APIRouter(prefix="/eval")

EVAL_ERRORS: dict[int | str, dict[str, object]] = {
    **ADMIN_ERRORS,
    409: {"model": ErrorResponse, "description": "Another benchmark is running"},
}


class EvalStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["retrieval", "answers"]
    provider: str | None = None  # answers only; default = the configured default


class EvalRunOut(BaseModel):
    id: str
    kind: str
    provider: str | None
    model: str | None
    status: str
    started_at: str
    finished_at: str | None
    total: int
    done: int
    summary: dict[str, Any] | None
    results: list[dict[str, Any]]
    error: str | None


class EvalListOut(BaseModel):
    runs: list[EvalRunOut]
    running: str | None  # id of the run in progress


def get_runner(request: Request) -> EvalRunner:
    runner: EvalRunner | None = request.app.state.eval_runner
    if runner is None:
        raise HistoryDisabledError("Benchmark runs are stored in the history, which is disabled.")
    return runner


Runner = Annotated[EvalRunner, Depends(get_runner)]


def _out(run: EvalRun) -> dict[str, Any]:
    return asdict(run)


@router.get("", response_model=EvalListOut, responses=ADMIN_ERRORS)
async def list_runs(history: History, runner: Runner) -> Any:
    """Recent runs, newest first (without per-question results)."""
    runs = await history.list_eval_runs()
    running = runner.running.id if runner.running else None
    return {"runs": [_out(r) for r in runs], "running": running}


@router.post("", status_code=202, response_model=EvalRunOut, responses=EVAL_ERRORS)
async def start_run(
    body: EvalStartIn, runner: Runner, services: Annotated[Services, Depends(get_services)]
) -> Any:
    """Starts a benchmark in the background. Answer runs call the LLM for every question
    (about $0.20 with Claude Opus; about 20 minutes with the local model on a CPU)."""
    return _out(await runner.start(body.kind, services, body.provider))


@router.get("/{run_id}", response_model=EvalRunOut, responses=ADMIN_ERRORS)
async def get_run(run_id: str, history: History, runner: Runner) -> Any:
    """One run with per-question results (live while it runs)."""
    if runner.current and runner.current.id == run_id:
        return _out(runner.current)
    run = await history.get_eval_run(run_id)
    if run is None:
        raise NotFoundError(f"No benchmark run {run_id!r}.")
    return _out(run)


@router.post("/{run_id}/cancel", status_code=202, responses=ADMIN_ERRORS)
async def cancel_run(run_id: str, runner: Runner) -> dict[str, bool]:
    """Stops a running benchmark after the current question."""
    if not runner.cancel(run_id):
        raise NotFoundError(f"Run {run_id!r} is not running.")
    return {"cancelled": True}
