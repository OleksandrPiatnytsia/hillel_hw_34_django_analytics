# Analytics: bookstore sales analytics

The second half of the final Hillel Python Pro homework. Analytics receives the order events of
the [bookstore](https://github.com/OleksandrPiatnytsia/hillel_hw_33_django_ci_cd_deploy) through
RabbitMQ and shows sales reports to analysts. The bookstore reads the same reports through the
REST API.

> Work in progress: stage 2 of 6 (the event consumer). The reports and the architecture diagram
> come in the next stages.

## Stack

Django 6.1, Django REST Framework, JWT (simplejwt), drf-spectacular (Swagger), PostgreSQL 17,
Redis 8, RabbitMQ (kombu), Celery, gunicorn + uvicorn, nginx, Docker Compose, Bootstrap 5, Sentry.
Interface languages: Ukrainian and English.

## Events

The bookstore publishes `order.created`, `order.paid` and `order.cancelled` to RabbitMQ. The
`consumer` service stores them exactly once. The contract and what happens on errors are
described in [docs/events.md](docs/events.md).

## Run in Docker

RabbitMQ lives in the bookstore's docker compose, so **start the bookstore first**. Its network
`bookstore_net` must exist.

```bash
cp .env.example .env          # set DJANGO_SECRET_KEY, POSTGRES_PASSWORD, RABBITMQ_* (as in the bookstore)
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
```

| Address                          | What                         |
|----------------------------------|------------------------------|
| http://localhost:8010/           | dashboard (log in first)     |
| http://localhost:8010/admin/     | admin                        |
| http://localhost:8010/api/docs/  | Swagger                      |
| http://localhost:8010/health/    | health check (PostgreSQL + Redis) |
| http://localhost:15672/          | RabbitMQ panel (bookstore's compose) |

Ports differ from the bookstore's (8000 / 5432 / 6379), so both projects can run at the same time.

## Run locally (runserver)

```bash
pip install -r requirements-dev.txt
docker compose up -d db redis            # PostgreSQL on :5433, Redis on :6380
python manage.py migrate
python manage.py runserver 8011
```

## Access

| Group     | Can                                                               |
|-----------|-------------------------------------------------------------------|
| Analysts  | the dashboard and the reports (`users.view_analytics`)            |
| Services  | the reports through the REST API with JWT (`users.use_reports_api`) |

The groups are created by `migrate`. Accounts are created by an admin; there is no sign-up.

## Tests and code style

```bash
pytest                 # coverage report, fails below 70%
black --check . && flake8
pre-commit install     # once per clone: black + flake8 before every commit
```

## License

MIT
