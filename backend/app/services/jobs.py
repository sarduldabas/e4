"""Background jobs: one worker thread pool, one job per report at a time, progress stored in the jobs table."""
from __future__ import annotations

import logging
import threading
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

from ..db import Database
from ..models import Job, now

log = logging.getLogger("jobs")


class Busy(Exception):
    pass


class Progress:
    def __init__(self, db: Database, job_id: str):
        self._db, self.job_id, self._lock = db, job_id, threading.Lock()
        self._log: list[str] = []

    def update(self, step: str, done: int | None = None, total: int | None = None, message: str | None = None) -> None:
        with self._lock:
            if message:
                self._log = (self._log + [message])[-30:]
            with self._db.session() as s:
                j = s.get(Job, self.job_id)
                if j:
                    p = dict(j.progress or {})
                    p["step"] = step
                    if done is not None:
                        p["done"] = done
                    if total is not None:
                        p["total"] = total
                    p["log"] = list(self._log)
                    j.progress = p


class JobRunner:
    def __init__(self, db: Database, workers: int = 2, inline: bool = False):
        self._db, self._inline = db, inline
        self._pool = None if inline else ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")
        self._futures: dict[str, Future] = {}
        self._lock = threading.Lock()

    def active(self, report_id: str) -> Job | None:
        with self._db.session() as s:
            return s.query(Job).filter(Job.report_id == report_id, Job.status.in_(["queued", "running"])).first()

    def submit(self, report_id: str, kind: str, fn: Callable[[Progress], None]) -> str:
        with self._lock:
            if self.active(report_id):
                raise Busy("another step is still running for this report")
            with self._db.session() as s:
                job = Job(report_id=report_id, kind=kind, status="queued", progress={"step": "queued", "log": []})
                s.add(job)
                s.flush()
                job_id = job.id
        if self._inline:
            self._execute(job_id, fn)
        else:
            self._futures[job_id] = self._pool.submit(self._execute, job_id, fn)
        return job_id

    def _execute(self, job_id: str, fn: Callable[[Progress], None]) -> None:
        with self._db.session() as s:
            j = s.get(Job, job_id)
            j.status, j.started_at = "running", now()
        prog = Progress(self._db, job_id)
        try:
            fn(prog)
            status, error = "done", None
        except Exception as e:  # noqa: BLE001  the job must always end in a final state
            log.error("job %s failed: %s", job_id, traceback.format_exc())
            status, error = "failed", f"{e.__class__.__name__}: {e}"[:1000]
        with self._db.session() as s:
            j = s.get(Job, job_id)
            j.status, j.error, j.finished_at = status, error, now()

    def wait(self, job_id: str, timeout: float = 120) -> None:
        f = self._futures.get(job_id)
        if f:
            f.result(timeout=timeout)

    def shutdown(self) -> None:
        if self._pool:
            self._pool.shutdown(wait=False, cancel_futures=True)

    def recover(self) -> None:
        """A job that was running when the service stopped can not continue: mark it failed so the user can start again."""
        with self._db.session() as s:
            for j in s.query(Job).filter(Job.status.in_(["queued", "running"])).all():
                j.status, j.error, j.finished_at = "failed", "Interrupted: the service was restarted.", now()
