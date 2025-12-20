from celery import Celery
from app.core.config import settings

celery = Celery("worker", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.task_routes = {"app.workers.tasks.*": {"queue": "default"}}
