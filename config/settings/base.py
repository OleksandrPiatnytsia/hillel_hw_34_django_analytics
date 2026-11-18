"""Settings shared by every environment.

The settings are a package; DJANGO_SETTINGS_MODULE picks one module, and
each of them starts with "from .base import *" and changes only its part:

    config.settings.development  runserver on your machine: DEBUG, Debug
                                 Toolbar, DEBUG logs (manage.py default)
    config.settings.production   Docker, Railway: DEBUG off, HTTPS and
                                 security headers, hashed static files
                                 (default of asgi.py / wsgi.py / celery.py
                                 and set in the Dockerfile)
    config.settings.test         pytest (pytest.ini): fast hasher, cache in
                                 memory, eager Celery

This file is safe on its own: DEBUG is off, and everything secret or
different per machine comes from environment variables (.env locally, the
variables of the service on a hosting).
https://docs.djangoproject.com/en/6.1/ref/settings/
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

from celery.schedules import crontab
from django.utils.translation import gettext_lazy as _
from dotenv import load_dotenv

from config.env import database_settings, env_list, rabbitmq_url, redis_url
from config.version import __version__, deployed_commit

# The project folder (the one with manage.py): three levels above this file
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Variables from .env in the project folder (runserver, pytest on the Mac).
# In Docker the same file comes through env_file in docker-compose.yml.
load_dotenv(BASE_DIR / ".env")


# Signs sessions, CSRF tokens and the JWT tokens: required, no default.
# A default in the code would be the same on every server, and anyone who
# reads the repository could forge a login.
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

# Off here; only development.py turns it on
DEBUG = False

# Host names the service answers to, comma separated. Any other host -> 400.
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # REST API: the reports for the bookstore (stage 4), JWT, Swagger
    "rest_framework",
    # Not for models (no token blacklist): its translations of the error
    # messages ("Token is invalid or expired") come with the app
    "rest_framework_simplejwt",
    "drf_spectacular",
    # Local apps
    "users",
    # The journal of the bookstore events + the consumer (RabbitMQ)
    "events",
    # Books and categories, as the events describe them
    "catalog",
    # Orders and their lines, as the events describe them
    "sales",
    # The dashboard now; the report tables and pages come at stage 4
    "reports",
]

# Custom user model. Must be set before the very first `migrate`: the admin
# log, groups and permissions get a foreign key to this model's table.
AUTH_USER_MODEL = "users.User"

# Where LoginRequiredMixin sends anonymous users, and where login / logout
# lead when there is no ?next=
LOGIN_URL = "users:login"
LOGIN_REDIRECT_URL = "reports:dashboard"
LOGOUT_REDIRECT_URL = "users:login"

MIDDLEWARE = [
    # Our middleware, first: its timer covers every middleware below + the view
    "config.middleware.RequestTimingMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # production.py inserts WhiteNoise here (Railway has no nginx)
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Chooses the language of every request (see "Internationalization").
    # After SessionMiddleware, before CommonMiddleware (Django docs).
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Are we running the tests? pytest-django imports the settings after pytest
# itself, so "pytest" is already loaded.
TESTING = "test" in sys.argv or "pytest" in sys.modules

# Django Debug Toolbar: turned on in development.py only
ENABLE_DEBUG_TOOLBAR = False

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Project-wide templates (base.html, navbar, error pages)
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # "app_version" and "app_commit": the footer of base.html
                "config.context_processors.version",
            ],
        },
    },
]

# The version in the footer (config/version.py)
APP_VERSION = __version__
APP_COMMIT = deployed_commit()
APP_REPOSITORY_URL = "https://github.com/OleksandrPiatnytsia/hillel_hw_34_django_analytics"
# The other half of the homework, linked from the footer
BOOKSTORE_REPOSITORY_URL = "https://github.com/OleksandrPiatnytsia/hillel_hw_33_django_ci_cd_deploy"

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# Database: PostgreSQL only
#
# The connection comes from environment variables, one of:
#   - DATABASE_URL=postgresql://user:password@host:5432/name (Railway, CI);
#   - POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD + POSTGRES_HOST /
#     POSTGRES_PORT (.env and docker-compose.yml). The postgres Docker image
#     reads the same names and creates the database on its first start.
# Analytics has its OWN database (port 5433 on the Mac), never the one of
# the bookstore: the services share data only through events and the API.
_database = database_settings()

DATABASES = {
    "default": {
        **_database,
        # A POOL of open connections instead of persistent connections
        # (CONN_MAX_AGE): under ASGI the ORM runs in worker threads, and a
        # persistent connection per thread would stay open after the thread
        # is gone. CONN_MAX_AGE must stay 0 with a pool (Django checks it).
        "CONN_MAX_AGE": 0,
        "OPTIONS": {
            **_database["OPTIONS"],
            "pool": {
                "min_size": 2,
                "max_size": 10,
                "timeout": 10,
            },
        },
    }
}


# Cache: Redis
#
# REDIS_URL: the address of the Redis server of Analytics (its own one, port
# 6380 on the Mac; redis://redis:6379 inside docker compose). One server,
# two databases (config/env.py redis_url): 0 = the cache and sessions,
# 1 = the Celery queue.
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6380")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": redis_url(REDIS_URL, 0),
        # Every deploy starts with its own, empty set of keys: the new code
        # never reads what the old code cached (report answers of the old
        # format). No commit (runserver, local Docker): no prefix.
        "KEY_PREFIX": APP_COMMIT[:7],
    }
}

# Sessions: read from the cache, written to both the cache and the
# database, so the logins survive a Redis restart
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"


# Celery: background tasks (config/celery.py, <app>/tasks.py)
#
# Every CELERY_* setting is a Celery setting without the prefix.
# The broker is Redis database 1 (the cache is in database 0, a FLUSHDB of
# one never touches the other). RabbitMQ is only for the bookstore events.
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL") or redis_url(REDIS_URL, 1)
# No result backend: nobody waits for a return value; the outcome of every
# task is in the log (the exports keep their state in the database, stage 4)
CELERY_TASK_IGNORE_RESULT = True
# Keep trying to connect to Redis while the worker starts (Redis may start a
# second later than the worker); Celery 5 warns without it
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# A message is removed from the queue only AFTER the task has finished: a
# worker killed in the middle doesn't lose it, another worker runs it again.
# Our tasks must be safe to run twice.
CELERY_TASK_ACKS_LATE = True
# One task at a time per worker process: a long export doesn't hold a pile
# of reserved messages that other processes could run
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
# A task that runs longer is stopped: soft -> SoftTimeLimitExceeded inside
# the task, hard -> the process is killed
CELERY_TASK_SOFT_TIME_LIMIT = 5 * 60
CELERY_TASK_TIME_LIMIT = 6 * 60
# Logging of the worker stays with LOGGING below. By default Celery removes
# the handlers of the "celery" logger at start, and its lines go nowhere.
CELERY_WORKER_HIJACK_ROOT_LOGGER = False

# Celery Beat: the schedule of periodic tasks (service "celery-beat").
# Kept in code, not in the admin: the schedule is reviewed in git.
# Stage 4 adds the recalculation of the reports here.
CELERY_BEAT_SCHEDULE = {
    # Expired sessions out of the django_session table, at 03:00 UTC
    "clear-expired-sessions": {
        "task": "users.tasks.clear_expired_sessions",
        "schedule": crontab(hour=3, minute=0),
    },
}


# Events of the bookstore: RabbitMQ (events/topology.py, docs/events.md)
#
# RabbitMQ runs in the bookstore's docker compose (the producer must work
# without Analytics); Analytics joins its network "bookstore_net". It
# carries ONLY the events; the Celery broker stays Redis.
#   bookstore.events (topic) --order.*--> analytics.events (quorum queue)
#   a message that fails EVENTS_DELIVERY_LIMIT times, or breaks the contract
#   --> analytics.dlx (fanout) --> analytics.events.dead
RABBITMQ_URL = rabbitmq_url()
EVENTS_EXCHANGE = "bookstore.events"
EVENTS_QUEUE = "analytics.events"
EVENTS_ROUTING_KEY = "order.*"
EVENTS_DEAD_LETTER_EXCHANGE = "analytics.dlx"
EVENTS_DEAD_LETTER_QUEUE = "analytics.events.dead"
# Deliveries of one message before RabbitMQ moves it to the dead letter
# queue: a bug in our code must not block the queue forever
EVENTS_DELIVERY_LIMIT = 5
# The consumer touches this file about once a second; the healthcheck of the
# "consumer" service in docker-compose.yml checks its age
CONSUMER_HEARTBEAT_FILE = os.getenv("CONSUMER_HEARTBEAT_FILE", "/tmp/analytics-consumer-alive")


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
#
# Two languages: Ukrainian (default) and English. The texts in the code and
# the templates are in English (msgid); the Ukrainian translations are in
# locale/uk/LC_MESSAGES/django.po (compiled to django.mo).
#
# The language of a request (LocaleMiddleware), first match wins:
#   1. the "django_language" cookie, set by the switcher in the navbar;
#   2. the Accept-Language header of the browser;
#   3. LANGUAGE_CODE.

LANGUAGE_CODE = "uk"

LANGUAGES = [
    ("uk", _("Ukrainian")),
    ("en", _("English")),
]

LOCALE_PATHS = [BASE_DIR / "locale"]

# The language cookie lives a year (default: until the browser is closed)
LANGUAGE_COOKIE_AGE = 365 * 24 * 60 * 60

# UTC, the same as the bookstore: the times in the events and in the
# reports are compared without conversions
TIME_ZONE = "UTC"
CELERY_TIMEZONE = TIME_ZONE

USE_I18N = True

USE_TZ = True


# Static files (CSS, images). Bootstrap and Chart.js come from a CDN.

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
# collectstatic output: in Docker the static_data volume, served by nginx
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    # Plain names, no collectstatic needed (runserver, the tests);
    # production.py replaces it with the hashed names
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


# REST API
# https://www.django-rest-framework.org/api-guide/settings/

REST_FRAMEWORK = {
    # JWT for other services (the bookstore calls the reports with the token
    # of its service account); the session for Swagger in the same browser
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Closed by default: a new endpoint without its own permission_classes
    # requires a login instead of being open by mistake
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # Getting a token = checking a password: a low limit against password
    # guessing (users.api.ThrottledTokenObtainPairView). Counters live in
    # the cache; over the limit: 429 + Retry-After.
    "DEFAULT_THROTTLE_RATES": {
        "token": "10/minute",
    },
    # REMOTE_ADDR only: behind nginx it is already the real client address
    # (forwarded_allow_ips in gunicorn.conf.py), and X-Forwarded-For from a
    # client could be made up to dodge the limit
    "NUM_PROXIES": 0,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# JWT tokens (djangorestframework-simplejwt)
#   POST /api/token/          {"username", "password"} -> {"access", "refresh"}
#   POST /api/token/refresh/  {"refresh"}              -> {"access"}
# A short access token: a stolen one works only for 15 minutes.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# API documentation: /api/schema/ (OpenAPI), /api/docs/ (Swagger UI)
SPECTACULAR_SETTINGS = {
    "TITLE": "Analytics API",
    "DESCRIPTION": (
        "Sales reports of the bookstore. Authentication: JWT "
        '(POST /api/token/, then the header "Authorization: Bearer <access>") '
        "or the session of the site login."
    ),
    "VERSION": __version__,
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_SETTINGS": {
        # Swagger remembers the token after "Authorize" until the page closes
        "persistAuthorization": True,
    },
}


# Logging
#
# Loggers are named after modules: logging.getLogger(__name__) in
# users/signals.py gives "users.signals", a child of "users" below.

LOGS_DIR = BASE_DIR / "logs"
# RotatingFileHandler doesn't create folders; logs/ is not in git
LOGS_DIR.mkdir(exist_ok=True)

# Our own code: INFO and above (development.py: DEBUG)
APP_LOG_LEVEL = "INFO"
# Loggers of our apps
APP_LOGGERS = ("users", "events", "catalog", "sales", "reports")

LOGGING = {
    "version": 1,
    # Keep Django's own loggers (django.server prints runserver requests)
    "disable_existing_loggers": False,
    "formatters": {
        # 2026-11-18 21:15:03,512 INFO users.signals Login: user=ann ip=127.0.0.1
        "verbose": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "filters": {
        "hide_client_error_traceback": {
            "()": "config.logging_filters.HideClientErrorTraceback",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["hide_client_error_traceback"],
        },
        "file": {
            # app.log -> app.log.1 at 1 MB, only the 5 newest are kept
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "app.log",
            "maxBytes": 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
            "formatter": "verbose",
            "filters": ["hide_client_error_traceback"],
        },
    },
    "loggers": {
        # Django itself: only problems (404 / 403 as WARNING, 500 as ERROR)
        "django": {
            "handlers": ["console", "file"],
            "level": "WARNING",
        },
        **{
            name: {
                "handlers": ["console", "file"],
                "level": APP_LOG_LEVEL,
                # No duplicates through the root logger
                "propagate": False,
            }
            for name in APP_LOGGERS
        },
        # config.middleware.RequestTimingMiddleware: one line per request
        "config": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        # Celery itself: "Task ... received / succeeded / retry", worker start
        "celery": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# RequestTimingMiddleware logs requests slower than this as WARNING
REQUEST_SLOW_MS = 500


# Sentry (sentry.io): errors of the service and of the Celery tasks.
# A separate Sentry project from the bookstore, so the errors of the two
# services don't mix. Empty SENTRY_DSN -> Sentry is off. See config/sentry.py.
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
# "local" for runserver, "docker" in docker-compose.yml: a filter in Sentry
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "local")
# Part of the requests and tasks timed in Sentry -> Performance (0 = errors only)
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

if not TESTING:
    # Imported only when needed: the tests never load the Sentry SDK
    from config.sentry import init_sentry

    init_sentry(
        SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    )
