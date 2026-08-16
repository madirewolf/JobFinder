"""In-process background-job registry for the web UI.

Long-running operations (ingest, classify, draft) get launched as asyncio
Tasks; their progress + log lines + final cost get tracked in a singleton
registry that the status page polls. The registry lives in process memory —
single-process personal-use bot, no Redis/Celery needed.

Lifecycle:
    POST /run/<action>      → registry.start(action_name, coro_factory) → returns Job
    GET  /run/job/<job_id>  → renders job.snapshot() (auto-refresh every 2s)
    Job logs lines via job.log("...") from inside the coroutine.
    Final state set via job.finish(error=None|str, cost=0.0).

Persistence: NONE. If the process restarts, in-flight jobs are lost. The
operations themselves write their own DB state (postings, applications,
etc.), so a lost status page only loses the *progress display*, not the
data. Fine for personal use.
"""

from __future__ import annotations

import asyncio
import secrets
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..logging_config import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class Job:
    id: str
    name: str                       # human label, e.g. "Pull new postings"
    action: str                     # internal slug, e.g. "ingest"
    started_at: float
    ended_at: float | None = None
    status: str = "running"         # 'running' | 'done' | 'error'
    error: str | None = None
    log_lines: list[str] = field(default_factory=list)
    cost_so_far_usd: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)
    _task: asyncio.Task | None = None

    def log_line(self, msg: str) -> None:
        """Append a human-readable progress line. Cap at 200 lines so a
        run-away job doesn't OOM the registry."""
        if len(self.log_lines) >= 200:
            self.log_lines.pop(0)
        self.log_lines.append(msg)

    def add_cost(self, usd: float) -> None:
        self.cost_so_far_usd += float(usd or 0.0)

    def finish(self, *, error: str | None = None) -> None:
        self.ended_at = time.time()
        self.status = "error" if error else "done"
        self.error = error

    @property
    def elapsed_s(self) -> float:
        end = self.ended_at if self.ended_at is not None else time.time()
        return max(0.0, end - self.started_at)

    def snapshot(self) -> dict[str, Any]:
        """Plain dict for templates."""
        return {
            "id": self.id,
            "name": self.name,
            "action": self.action,
            "status": self.status,
            "error": self.error,
            "log_lines": list(self.log_lines),
            "cost_so_far_usd": round(self.cost_so_far_usd, 4),
            "elapsed_s": round(self.elapsed_s, 1),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "extra": dict(self.extra),
        }


class JobRegistry:
    """Singleton-ish registry. One instance per FastAPI app."""

    def __init__(self, *, max_jobs_kept: int = 50) -> None:
        self._jobs: dict[str, Job] = {}
        self._max = max_jobs_kept
        self._lock = asyncio.Lock()

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        """Newest-first."""
        return sorted(self._jobs.values(), key=lambda j: j.started_at, reverse=True)

    def is_running(self, action: str) -> Job | None:
        """Return the in-flight job for `action` if one is currently running.

        Used to prevent the user accidentally kicking off two `ingest`s at
        the same time — the action button shows "already running" instead.
        """
        for job in self._jobs.values():
            if job.action == action and job.status == "running":
                return job
        return None

    def start(
        self,
        *,
        action: str,
        name: str,
        coro_factory: Callable[[Job], Awaitable[Any]],
    ) -> Job:
        """Register a Job and launch its coroutine as a background task.

        `coro_factory(job)` builds the coroutine — it gets the Job so it can
        call `job.log_line(...)` and `job.add_cost(...)` as it runs.

        Returns the Job immediately (request returns fast; work continues).
        """
        # Trim oldest finished jobs if we're over cap
        if len(self._jobs) >= self._max:
            stale = sorted(
                (j for j in self._jobs.values() if j.status != "running"),
                key=lambda j: j.ended_at or 0,
            )
            for j in stale[: max(0, len(self._jobs) - self._max + 1)]:
                self._jobs.pop(j.id, None)

        job_id = secrets.token_urlsafe(8)
        job = Job(id=job_id, name=name, action=action, started_at=time.time())
        self._jobs[job_id] = job

        async def _runner() -> None:
            try:
                await coro_factory(job)
                job.finish(error=None)
                log.info("ui.job.done", job_id=job.id, action=action,
                         elapsed_s=round(job.elapsed_s, 2),
                         cost=round(job.cost_so_far_usd, 4))
            except asyncio.CancelledError:
                job.finish(error="cancelled")
                raise
            except Exception as e:  # noqa: BLE001
                job.finish(error=f"{type(e).__name__}: {e}")
                job.log_line(f"❌ ERROR: {e}")
                tb = traceback.format_exc()
                for line in tb.splitlines()[-12:]:  # last 12 lines is plenty
                    job.log_line(line)
                log.error("ui.job.fail", job_id=job.id, action=action,
                          error=str(e))

        job._task = asyncio.create_task(_runner())
        log.info("ui.job.start", job_id=job.id, action=action, name=name)
        return job


# Module-level singleton bound at app-creation time
_REGISTRY: JobRegistry | None = None


def get_registry() -> JobRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = JobRegistry()
    return _REGISTRY


# ─────────────────────────────────────────────────────────────────────────────
# Action catalog — what the /run page shows and what each button does.
# Cost numbers are rough estimates the user sees BEFORE confirming.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(slots=True, frozen=True)
class Action:
    slug: str
    title: str            # button label
    description: str      # plain-English what-it-does
    cost_label: str       # "$0", "~$0.01/posting", etc.
    cost_bucket: str      # 'free' | 'cheap' | 'paid' (drives confirm dialog)
    requires_confirm: bool


ACTIONS: dict[str, Action] = {
    "ingest": Action(
        slug="ingest",
        title="1. Pull new postings",
        description="Hit every seeded company's careers page and pull any new openings into the database. No LLM calls — just web scraping.",
        cost_label="Free",
        cost_bucket="free",
        requires_confirm=False,
    ),
    "classify": Action(
        slug="classify",
        title="2. Score new postings",
        description="Run regex + embeddings (free) and then a Haiku call (cheap) to assign each posting a fit score. Postings that haven't been scored before are processed.",
        cost_label="~$0.01 per new posting",
        cost_bucket="cheap",
        requires_confirm=True,
    ),
    "profile_ingest": Action(
        slug="profile_ingest",
        title="Re-ingest your profile",
        description="Re-chunk and re-embed your master résumé + project files. Run this any time you edit profile/*.md.",
        cost_label="Free",
        cost_bucket="free",
        requires_confirm=False,
    ),
    "draft": Action(
        slug="draft",
        title="3. Generate drafts for queued jobs",
        description="For every posting you've queued: a Haiku fit-gate decides whether to skip; if it passes, Sonnet produces a tailored cover letter, summary, skills order, etc. Skipped postings cost only the gate.",
        cost_label="~$0.01–0.06 per posting",
        cost_bucket="paid",
        requires_confirm=True,
    ),
}
