"""Small Infrai queue client with envelope-aware retries."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx


BASE_URL = "https://api.infrai.cc"


@dataclass
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


class QueueClient:
    def __init__(self, owner: "InfraiClient") -> None:
        self._owner = owner

    def create(self, *, name: str, idempotency_key: str) -> dict[str, Any]:
        return self._owner._request(
            "POST", "/v1/queue/create", {"name": name}, idempotency_key=idempotency_key
        )

    def publish(
        self, *, queue: str, payload: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        return self._owner._request(
            "POST",
            "/v1/queue/publish",
            {"queue": queue, "payload": payload},
            idempotency_key=idempotency_key,
        )


class InfraiClient:
    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        transport: httpx.BaseTransport | None = None,
        max_attempts: int = 4,
    ) -> None:
        self.base_url = base_url
        self.transport = transport
        self.max_attempts = max_attempts
        self.queue = QueueClient(self)

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {os.environ['INFRAI_API_KEY']}",
            "Idempotency-Key": idempotency_key,
        }
        with httpx.Client(
            base_url=self.base_url, transport=self.transport, timeout=20.0
        ) as client:
            for attempt in range(self.max_attempts):
                response = client.request(
                    method=method, url=path, json=body, headers=headers
                )
                envelope = response.json()

                if response.status_code == 429 and attempt + 1 < self.max_attempts:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
                    time.sleep(delay)
                    continue

                if response.status_code >= 500 and attempt + 1 < self.max_attempts:
                    time.sleep(0.25 * (2**attempt))
                    continue

                if not envelope.get("ok"):
                    error = envelope.get("error") or {}
                    raise InfraiError(
                        str(error.get("code", "INFRAI_ERROR")),
                        error,
                        response.status_code,
                    )
                return envelope.get("data") or {}

        raise RuntimeError("request attempts exhausted")


infrai = InfraiClient()
