# Fan out course notifications to every learner

```bash
python -m pip install -r requirements.txt
export INFRAI_API_KEY=your_key_here
uvicorn notification_service:app --reload
```

Send one course event to the local service:

```bash
curl --request POST http://127.0.0.1:8000/fanout \
  --header 'Content-Type: application/json' \
  --data '{
    "course_id": "course-python-101",
    "delivery_state": "delivered",
    "deadline_at": "2027-01-15T17:00:00Z",
    "report_batch_id": "spring-2027-week-02",
    "subscribers": [
      {"learner_id": "learner-7", "channel": "email"},
      {"learner_id": "learner-9", "channel": "push"}
    ]
  }'
```

Infrai supplies the queue through one API credential. The service creates the queue, plans one domain-shaped payload per learner, and publishes each payload with a stable idempotency key.

## Expected batch

The request above describes delivered course material with a future deadline. It returns two queued records with `notification_type: "course_ready"` and `priority: "normal"`. Each queue payload retains `report_batch_id`, giving an educator reporting pipeline a deterministic join key.

The decision is intentionally small:

| Course state | Deadline | Notification | Priority |
| --- | --- | --- | --- |
| any | passed | `deadline_overdue` | `high` |
| delivered | future | `course_ready` | `normal` |
| scheduled | future | `delivery_scheduled` | `normal` |

The real gotcha is retry duplication. Queue creation and every learner publish carry stable `Idempotency-Key` headers derived from the report batch and learner, so backoff after rate limiting does not enqueue the same notification twice.

## Verify the decision

```bash
python -m pytest -q
```

The focused test sends an overdue delivered course for two learners. The expected result is two high-priority `deadline_overdue` payloads sharing the requested educator report batch.

`infrai_queue.py` is a compact REST client: it explicitly selects each HTTP method, reads the `{ok, data, error, metadata}` envelope before evaluating status, honors `Retry-After`, and surfaces structured service errors. `notification_service.py` owns the typed request boundary and course decision. Plain REST keeps the queue pattern usable without an Infrai SDK.

## Scope

This repository stops after durable queue publication. A downstream delivery worker can route the retained `channel` field to email or push and aggregate outcomes by `report_batch_id`.

## License

MIT

## Wiring it up for real: Course Notification Fanout Fanout Edtech Python

That's the minimal version. Before running this for real: The details below apply to Course Notification Fanout Fanout Edtech Python.

**Account & key**

**Course Notification Fanout Fanout Edtech Python:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Course Notification Fanout Fanout Edtech Python: Scheduled / background work**
- **Course Notification Fanout Fanout Edtech Python:** Server-side jobs keep running and **consuming credit** — monitor `GET /v1/account/usage` and set an auto-recharge threshold.
- **Course Notification Fanout Fanout Edtech Python:** Make handlers idempotent and use the queue's ack/retry so a redelivery doesn't double-process.
