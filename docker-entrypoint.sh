#!/bin/sh
# Entrypoint of the containers built from the Dockerfile (web, celery,
# celery-beat): prepares Django, then starts the command.
#
# Docker runs it as ENTRYPOINT with the CMD as arguments:
#   docker-entrypoint.sh gunicorn config.asgi:application
#   docker compose run --rm web python manage.py createsuperuser
#     -> docker-entrypoint.sh python manage.py createsuperuser
#
# PostgreSQL is already accepting connections here: web has
# depends_on: db: condition: service_healthy in docker-compose.yml.

# Stop at the first failing command: a failed migrate must not be followed
# by gunicorn on a database with a wrong schema
set -e

# Only the web server (gunicorn) runs migrate + collectstatic. Several
# containers running migrate at the same moment could apply the same
# migration twice ("relation already exists"); celery, celery-beat and the
# consumer start only after web is healthy (depends_on). One-off commands
# (docker compose run web python manage.py ...) skip them too: they work
# with the database web has already migrated.
if [ "$1" = "gunicorn" ]; then
    echo "Applying database migrations..."
    # --noinput: never ask questions (nobody can answer them in a container)
    python manage.py migrate --noinput

    echo "Collecting static files..."
    python manage.py collectstatic --noinput
fi

echo "Starting: $*"
# exec: gunicorn replaces this shell and becomes PID 1, so it gets SIGTERM
# from `docker compose stop` itself and shuts down cleanly
exec "$@"
