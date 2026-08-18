"""Deterministic local HTTP route double for generic adapter integration tests."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from typing import cast
from urllib.parse import urlsplit
from urllib.request import Request

from ragfence.adapters.generic_http import _HTTPResponse


class StubResponse:
    def __init__(self, status: int = 200, body: bytes = b"{}") -> None:
        self.status = status
        self._body = body

    def __enter__(self) -> StubResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


ResponseFactory = Callable[[Request, bytes], StubResponse | BaseException]


class GenericHTTPStub:
    """A route-table opener with FastAPI-like method/path dispatch semantics."""

    def __init__(self, base_url: str = "http://stub.local") -> None:
        self.base_url = base_url
        self.requests: list[tuple[str, str, object, dict[str, str]]] = []
        self._routes: dict[tuple[str, str], list[ResponseFactory]] = defaultdict(list)

    def route(
        self,
        method: str,
        path: str,
        *responses: StubResponse | BaseException | ResponseFactory,
    ) -> None:
        if not path.startswith("/"):
            path = "/" + path
        self._routes[(method.upper(), path)].extend(
            self._factory(response) for response in responses
        )

    def __call__(self, request: Request, timeout: float) -> _HTTPResponse:
        parsed = urlsplit(request.full_url)
        body = cast(bytes, request.data or b"")
        method = request.get_method()
        payload: object = None
        if body:
            try:
                payload = json.loads(body)
            except ValueError:
                payload = body
        self.requests.append(
            (
                method,
                parsed.path,
                payload,
                {key: value for key, value in request.header_items()},
            )
        )
        factories = self._routes[(method, parsed.path)]
        if not factories:
            return StubResponse(404, b"not found")
        response = factories.pop(0)(request, body)
        if isinstance(response, BaseException):
            raise response
        return response

    @staticmethod
    def _factory(response: StubResponse | BaseException | ResponseFactory) -> ResponseFactory:
        if callable(response):
            return response
        return lambda request, body: response


def json_response(payload: object, status: int = 200) -> StubResponse:
    return StubResponse(status, json.dumps(payload, separators=(",", ":")).encode())


def text_response(body: str, status: int = 200) -> StubResponse:
    return StubResponse(status, body.encode())
