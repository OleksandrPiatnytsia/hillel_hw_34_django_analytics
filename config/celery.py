"""The Celery application of the Analytics service.

How a background task works:

    web / beat                     Redis db 1 (broker)          worker (celery)
    task.delay()   -- message -->  queue "celery"  -- message -->  runs task()

    celery-beat: puts the periodic tasks of CELERY_BEAT_SCHEDULE into the
    same queue at their time; it runs nothing itself.

Start (docker-compose.yml runs the same):
    celery -A config worker --loglevel=info
    celery -A config beat --loglevel=info

The tasks live in <app>/tasks.py (@shared_task) and are found by
autodiscover_tasks(). RabbitMQ is NOT the Celery broker: it carries only the
events of the bookstore, read by a separate consumer (stage 2).
"""

import os

from celery import Celery

# Celery is started as its own program (celery -A config ...), not by
# manage.py: it must know the settings module itself. Production by default,
# like asgi.py / wsgi.py. config/__init__.py imports this file, so this line
# runs first in every process that imports the config package; manage.py
# sets its own default (development) before that.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("config")
# Every Django setting that starts with CELERY_ is a Celery setting
# (CELERY_BROKER_URL -> broker_url)
app.config_from_object("django.conf:settings", namespace="CELERY")
# Import tasks.py of every app in INSTALLED_APPS
app.autodiscover_tasks()
