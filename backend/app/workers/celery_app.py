from datetime import timedelta

from celery import Celery
from app.core.config import settings

# `include` imports the tasks module on worker startup so the `@celery.task`
# decorators actually register. Without this the worker boots with an empty
# task list and the reminder sweep never runs.
celery = Celery(
    "worker",
    broker=settings.effective_redis_url,
    backend=settings.effective_redis_url,
    include=["app.workers.tasks"],
)
celery.conf.task_routes = {"app.workers.tasks.*": {"queue": "default"}}

# Periodic sweep for due reminders. Requires running a beat scheduler alongside
# the worker (`celery -A app.workers.celery_app.celery beat`). The worker itself
# only consumes; beat is what enqueues `enqueue_due_reminders` on this cadence.
celery.conf.beat_schedule = {
    "enqueue-due-reminders": {
        "task": "app.workers.tasks.enqueue_due_reminders",
        "schedule": timedelta(minutes=settings.reminder_sweep_interval_minutes),
    },
    "cleanup-expired-share-links": {
        "task": "app.workers.tasks.cleanup_expired_share_links",
        "schedule": timedelta(days=1),
    },
}
