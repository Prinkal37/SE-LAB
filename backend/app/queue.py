"""Job dispatch (NFR-5.1.2, section 3.4).

QUEUE_MODE=rq     -> push to Redis; `rq worker` processes jobs (scales independently of the API).
QUEUE_MODE=inline -> FastAPI BackgroundTasks in the API process (local dev / tests, no Redis needed).
"""
import logging

from fastapi import BackgroundTasks

from .config import get_settings
from .pipeline import process_submission

log = logging.getLogger("avg.queue")


def enqueue(submission_ids: list[str], background: BackgroundTasks) -> None:
    s = get_settings()
    if s.queue_mode == "rq":
        try:
            from redis import Redis
            from rq import Queue

            q = Queue(s.queue_name, connection=Redis.from_url(s.redis_url))
            for sid in submission_ids:
                q.enqueue("app.pipeline.process_submission", sid, job_timeout=300, result_ttl=3600)
            return
        except Exception as e:
            log.warning("Redis unavailable (%s); processing in the API process instead.", e)
    for sid in submission_ids:
        background.add_task(process_submission, sid)


def queue_health() -> str:
    s = get_settings()
    if s.queue_mode != "rq":
        return "inline"
    try:
        from redis import Redis

        Redis.from_url(s.redis_url, socket_connect_timeout=1).ping()
        return "redis:ok"
    except Exception:
        return "redis:unreachable"
