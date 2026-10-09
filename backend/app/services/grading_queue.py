from __future__ import annotations

from dataclasses import dataclass
from queue import Queue
from threading import Lock, Thread
from typing import Literal

from flask import Flask

from ..extensions import db
from ..models import Assignment
from .grading import run_auto_grading_for_student


@dataclass(frozen=True)
class GradingJob:
    assignment_id: int
    student_user_id: int
    reason: str = "confirmed_submission"


_queue: Queue[GradingJob] = Queue()
_worker_lock = Lock()
_worker_started = False
_app: Flask | None = None


def init_grading_queue(app: Flask) -> None:
    global _app
    _app = app
    if app.config.get("GRADING_QUEUE_INLINE") or not app.config.get("GRADING_QUEUE_ENABLED", True):
        return
    _start_worker(app)


def enqueue_auto_grading(app: Flask, assignment_id: int, student_user_id: int, reason: str = "confirmed_submission") -> Literal["queued", "inline"]:
    job = GradingJob(assignment_id=assignment_id, student_user_id=student_user_id, reason=reason)
    if app.config.get("GRADING_QUEUE_INLINE"):
        _run_job(app, job)
        return "inline"
    _start_worker(app)
    _queue.put(job)
    return "queued"


def _start_worker(app: Flask) -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        worker = Thread(target=_worker_loop, args=(app,), name="sunjudge-grading-worker", daemon=True)
        worker.start()
        _worker_started = True


def _worker_loop(app: Flask) -> None:
    while True:
        job = _queue.get()
        try:
            _run_job(app, job)
        finally:
            _queue.task_done()


def _run_job(app: Flask, job: GradingJob) -> None:
    with app.app_context():
        assignment = db.session.get(Assignment, job.assignment_id)
        if not assignment:
            return
        try:
            run_auto_grading_for_student(assignment, job.student_user_id)
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception(
                "Auto grading job failed for assignment=%s student=%s reason=%s",
                job.assignment_id,
                job.student_user_id,
                job.reason,
            )
        finally:
            db.session.remove()
