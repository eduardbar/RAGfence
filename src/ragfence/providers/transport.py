"""Bounded stdlib JSON transport for provider tests and adapters."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any, cast
from urllib.error import URLError
from urllib.request import Request, urlopen

from .errors import LLMHTTPError, LLMRateLimitError, LLMResponseTooLargeError, LLMTimeoutError


class LLMHTTPTransport:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 30.0,
        max_response_bytes: int = 1_000_000,
        max_attempts: int = 1,
        backoff_seconds: float = 0.5,
        max_backoff_seconds: float = 30.0,
        max_retry_after_seconds: float = 60.0,
        opener: Callable[..., object] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.max_retry_after_seconds = max_retry_after_seconds
        self._opener = opener or cast(Callable[[Request, float], Any], urlopen)
        self._sleeper = sleeper

    def post_json(self, payload: object, headers: Mapping[str, str], path: str = "") -> object:
        url = self.base_url + (path if path.startswith("/") else ("/" + path if path else ""))
        body = json.dumps(payload, separators=(",", ":")).encode()
        for attempt in range(self.max_attempts):
            request_headers = {"Content-Type": "application/json", **headers}
            request = Request(url, data=body, headers=request_headers, method="POST")
            try:
                with self._opener(request, self.timeout_seconds) as response:  # type: ignore[union-attr]
                    status = response.status
                    if status == 429:
                        if attempt + 1 < self.max_attempts:
                            self._sleeper(self._delay(attempt, getattr(response, "headers", {})))
                            continue
                        raise LLMRateLimitError(status)
                    if not 200 <= status < 300:
                        if status >= 500 and attempt + 1 < self.max_attempts:
                            self._sleeper(
                                min(self.backoff_seconds * (2**attempt), self.max_backoff_seconds)
                            )
                            continue
                        raise LLMHTTPError(status)
                    raw = response.read(self.max_response_bytes + 1)
            except LLMHTTPError:
                raise
            except TimeoutError as exc:
                if attempt + 1 < self.max_attempts:
                    self._sleeper(
                        min(self.backoff_seconds * (2**attempt), self.max_backoff_seconds)
                    )
                    continue
                raise LLMTimeoutError() from exc
            except (OSError, URLError) as exc:
                raise LLMHTTPError(599) from exc
            if len(raw) > self.max_response_bytes:
                raise LLMResponseTooLargeError("provider response exceeded configured bound")
            return json.loads(raw)
        raise LLMHTTPError(599)

    def _delay(self, attempt: int, headers: object) -> float:
        value = headers.get("Retry-After") if isinstance(headers, Mapping) else None
        try:
            if value is not None:
                delay = float(cast(str, value))
                return min(delay, self.max_retry_after_seconds)
        except (TypeError, ValueError):
            pass
        return cast(float, min(self.backoff_seconds * (2**attempt), self.max_backoff_seconds))
