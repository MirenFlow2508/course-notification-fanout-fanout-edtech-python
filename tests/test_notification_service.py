from datetime import datetime, timezone

from fastapi.testclient import TestClient

from notification_service import app, infrai


def test_overdue_course_fans_out_high_priority_reporting_records(monkeypatch) -> None:
    published: list[dict] = []
    queue_client = getattr(infrai, "queue")
    monkeypatch.setattr(queue_client, "create", lambda **_: {})
    monkeypatch.setattr(
        queue_client,
        "publish",
        lambda *, queue, payload, idempotency_key: published.append(
            {"queue": queue, "payload": payload, "idempotency_key": idempotency_key}
        ),
    )
    client = TestClient(app)

    response = client.post(
        "/fanout",
        json={
            "course_id": "course-python-101",
            "delivery_state": "delivered",
            "deadline_at": datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat(),
            "report_batch_id": "report-2024-01",
            "subscribers": [
                {"learner_id": "learner-7", "channel": "email"},
                {"learner_id": "learner-9", "channel": "push"},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["queued_count"] == 2
    assert {item["queue"] for item in published} == {"course-notifications"}
    assert [item["payload"]["notification_type"] for item in published] == [
        "deadline_overdue",
        "deadline_overdue",
    ]
    assert all(item["payload"]["priority"] == "high" for item in published)
    assert {item["payload"]["report_batch_id"] for item in published} == {
        "report-2024-01"
    }
