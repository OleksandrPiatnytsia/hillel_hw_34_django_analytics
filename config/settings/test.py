"""Settings for the tests (pytest.ini: DJANGO_SETTINGS_MODULE = config.settings.test).

Everything from base.py (not development.py: no Debug Toolbar, DEBUG off,
like on a server), plus a few changes that make the tests fast, repeatable
and independent of the local .env:

- a fast password hasher: the default one (PBKDF2) makes every
  create_user() / login take ~0.3 s;
- the cache in memory instead of Redis: the tests don't touch the cache
  and sessions of the running service; conftest.py clears it before every test;
- no log file: test runs don't write to logs/app.log;
- Celery tasks run at once, without a broker and a worker.

The database stays PostgreSQL from .env (localhost:5433) or DATABASE_URL
(GitHub Actions): pytest-django creates a separate database "test_<name>",
the real data is never touched.
"""

# F401 + F403: flake8 can't see which names come from "*"; settings modules
# are read by Django, nothing here uses them by name
from .base import *  # noqa: F401, F403
from .base import DATABASES, LOGGING

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# No collected static files in tests ({% static %} still builds the URLs)
STATIC_ROOT = None

# Remove the "file" handler: dictConfig opens the file of every handler in
# the list, even an unused one. Records still go to the console handler,
# pytest shows them only for a failed test.
LOGGING["handlers"].pop("file")
for logger_config in LOGGING["loggers"].values():
    logger_config["handlers"] = [
        handler for handler in logger_config["handlers"] if handler != "file"
    ]

# No connection pool in tests: the pool keeps its connections open until
# the process ends, and pytest-django can't drop the test database at the
# end ("is being accessed by other users").
DATABASES["default"]["OPTIONS"].pop("pool", None)

# task.delay() runs the task right here, synchronously. EAGER_PROPAGATES:
# an error of a task fails the test instead of hiding in a log.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
