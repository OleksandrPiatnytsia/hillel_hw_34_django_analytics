# Events of the bookstore: the contract

The bookstore (producer) publishes these events to RabbitMQ, Analytics (consumer) reads them.
This file is the single description of the contract. The bookstore's repository links here.
In Analytics the contract is checked in code by `events/contract.py`.

## Transport

| What              | Value                                                              |
|-------------------|--------------------------------------------------------------------|
| Exchange          | `bookstore.events`, type `topic`, durable. Both sides declare it.  |
| Routing key       | the event type: `order.created`, `order.paid`, `order.cancelled`   |
| Queue (Analytics) | `analytics.events`, quorum, durable, bound with `order.*`          |
| Dead letters      | exchange `analytics.dlx` (fanout) to queue `analytics.events.dead` |

Properties of every message:

- `message_id`: the `event_id`;
- `content_type`: `application/json`, `content_encoding`: `utf-8`;
- `delivery_mode`: persistent (2).

The publisher uses **publisher confirms**. An event counts as sent only after RabbitMQ has
confirmed it. Until then it stays in the bookstore's outbox.

## Body, version 1

```json
{
  "event_id": "5b0e1c8e-8a4e-4c2a-9a35-1f9c2d0e7b11",
  "type": "order.paid",
  "version": 1,
  "occurred_at": "2026-11-18T10:15:00+00:00",
  "order": {
    "id": 42,
    "status": "processing",
    "payment_status": "paid",
    "created_at": "2026-11-18T10:00:00+00:00",
    "currency": "USD",
    "total": "25.00",
    "total_uah": "1037.50",
    "customer_key": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "items": [
      {
        "book": {
          "id": 7,
          "title": "Kobzar",
          "author": "Taras Shevchenko",
          "publisher": "A-BA-BA-HA-LA-MA-HA",
          "language": "uk",
          "categories": [{"id": 3, "name": "Poetry"}]
        },
        "format_type": "paper",
        "quantity": 2,
        "price": "12.50",
        "amount_uah": "1037.50"
      }
    ]
  }
}
```

| Field                  | Rules                                                                 |
|------------------------|-----------------------------------------------------------------------|
| `event_id`             | UUID, unique for each event. A repeated id is skipped as a duplicate. |
| `type`                 | `order.created` / `order.paid` / `order.cancelled`                    |
| `version`              | `1`. Another number goes to the dead letters.                         |
| `occurred_at`          | ISO 8601 with a time zone: when it happened in the bookstore          |
| `order`                | the WHOLE order at that moment (a snapshot), not only what changed    |
| `order.status`         | `new` / `processing` / `shipped` / `completed` / `cancelled`          |
| `order.payment_status` | `unpaid` / `partially_paid` / `paid`                                  |
| `order.currency`       | 3 letters, the currency of the order                                  |
| money                  | strings with 2 decimals (`"25.00"`), never floats                     |
| `total_uah`, `amount_uah` | already converted to UAH by the bookstore (it knows its NBU rate) |
| `customer_key`         | sha256 hex (64 characters) of the user id with a secret salt that only the bookstore knows (`CUSTOMER_KEY_SALT`) |
| `items`                | at least one; `format_type`: `paper` / `ebook` / `audio`              |
| `book.author`, `book.publisher`, `book.language` | may be empty strings                         |

**No personal data**: no names, emails, phones or addresses. Analytics stores only the fields
above. Any other field is dropped by the contract check.

## How Analytics processes an event

1. The body must be JSON and must match the table above. If not, the message is rejected at once
   and goes to the dead letters. Its `event_id`, if it can be read, is written to the journal as
   `failed`.
2. In ONE database transaction:
   - an `event_id` that is already processed is a duplicate and is skipped;
   - the order, its lines, its books and categories are created or updated from the snapshot;
   - the event is written to the journal (`events.Event`) as `processed`.
3. Only after the COMMIT is the message acknowledged.

Events may come in any order. Each one carries the whole order, and an older snapshot never
overwrites a newer one. `paid_at` and `cancelled_at` are set from the `occurred_at` of
`order.paid` and `order.cancelled`.

Failures:

| What                     | What happens                                                        |
|--------------------------|---------------------------------------------------------------------|
| breaks the contract      | dead letters at once                                                |
| the database is down     | the same message is retried after 1, 2, 4 ... 60 s until the database is back; nothing is lost |
| a bug in the consumer    | back to the queue; after 5 deliveries RabbitMQ moves it to the dead letters |
| RabbitMQ is down         | the bookstore keeps the events in its outbox; the consumer reconnects by itself |
| Analytics is down        | the events wait in the durable queue                                |

## Tools (Analytics)

```bash
python manage.py consume_events                       # the consumer (service "consumer")
python manage.py publish_test_event --type order.paid --order-id 1
python manage.py replay_dead_letters --dry-run        # list the dead letters
python manage.py replay_dead_letters                  # move them back after a fix
```

The RabbitMQ web panel of the bookstore's compose is at http://localhost:15672.
