"""Course notification fanout service."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from infrai_queue import InfraiError, infrai


class DeliveryState(str, Enum):
    scheduled = "scheduled"
    delivered = "delivered"


class Subscriber(BaseModel):
    learner_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)


class CourseFanoutRequest(BaseModel):
    course_id: str = Field(min_length=1)
    delivery_state: DeliveryState
    deadline_at: datetime
    report_batch_id: str = Field(min_length=1)
    subscribers: list[Subscriber] = Field(min_length=1)


class QueuedNotification(BaseModel):
    learner_id: str
    notification_type: str
    priority: str


class FanoutResult(BaseModel):
    course_id: str
    queued_count: int
    notifications: list[QueuedNotification]


app = FastAPI(title="Course notification fanout")
QUEUE_NAME = "course-notifications"


def plan_notification(
    request: CourseFanoutRequest, subscriber: Subscriber, now: datetime
) -> dict[str, Any]:
    overdue = request.deadline_at <= now
    if overdue:
        notification_type, priority = "deadline_overdue", "high"
    elif request.delivery_state == DeliveryState.delivered:
        notification_type, priority = "course_ready", "normal"
    else:
        notification_type, priority = "delivery_scheduled", "normal"

    return {
        "course_id": request.course_id,
        "learner_id": subscriber.learner_id,
        "channel": subscriber.channel,
        "notification_type": notification_type,
        "priority": priority,
        "deadline_at": request.deadline_at.isoformat(),
        "report_batch_id": request.report_batch_id,
    }


@app.exception_handler(InfraiError)
async def map_infrai_error(_: Request, error: InfraiError) -> JSONResponse:
    status = error.status_code if 400 <= error.status_code < 500 else 502
    return JSONResponse(
        status_code=status,
        content={"error": {"code": error.code, "detail": error.detail}},
    )


@app.post("/fanout", response_model=FanoutResult)
def fanout_notifications(request: CourseFanoutRequest) -> FanoutResult:
    infrai.queue.create(
        name=QUEUE_NAME, idempotency_key=f"queue:{request.report_batch_id}"
    )
    now = datetime.now(timezone.utc)
    queued: list[QueuedNotification] = []

    for subscriber in request.subscribers:
        payload = plan_notification(request, subscriber, now)
        infrai.queue.publish(
            queue=QUEUE_NAME,
            payload=payload,
            idempotency_key=(
                f"notification:{request.report_batch_id}:{subscriber.learner_id}"
            ),
        )
        queued.append(QueuedNotification(**payload))

    return FanoutResult(
        course_id=request.course_id,
        queued_count=len(queued),
        notifications=queued,
    )
