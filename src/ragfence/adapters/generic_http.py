"""Configuration, transport, and adapter for generic HTTP targets.

The adapter delegates I/O to :class:`GenericHTTPTransport` and keeps response
decoding at the strict mapping seam.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from collections.abc import Callable
from typing import Annotated, Literal, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from ragfence.core.enums import Classification
from ragfence.core.models import AuthorizationContext, RetrievalRequest, RetrievedChunk
from ragfence.evaluation.redaction import redact_secrets

from .errors import AdapterError, AdapterTransportError
from .mapping import map_answer_response, map_retrieve_response, require_answer_path

_MAX_HEALTH_RETRIES = 10
_MAX_BACKOFF_SECONDS = 60.0

ALLOWED_IDENTITY_PLACEHOLDERS: frozenset[str] = frozenset(
    {"{actor_user_id}", "{actor_tenant_id}", "{actor_department_id}"}
)
_PLACEHOLDER_RE = re.compile(r"\{([^}]*)\}")


def _relative_path(value: str) -> str:
    if not value or value.startswith(("/", "\\")) or "\\" in value:
        raise ValueError("endpoint paths must be non-empty relative paths")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("endpoint paths must be relative paths without query or fragment")
    if any(ord(char) < 32 for char in value):
        raise ValueError("endpoint paths must not contain control characters")
    return value


def _validate_identity_templates(templates: dict[str, str]) -> dict[str, str]:
    """Reject templates containing placeholders outside the allowlist (spec R4.2)."""
    for header_name, template in templates.items():
        for match in _PLACEHOLDER_RE.finditer(template):
            placeholder = f"{{{match.group(1)}}}"
            if placeholder not in ALLOWED_IDENTITY_PLACEHOLDERS:
                raise ValueError(
                    f"unknown placeholder {placeholder} in identity header {header_name!r}; "
                    f"allowed: {sorted(ALLOWED_IDENTITY_PLACEHOLDERS)}"
                )
    return templates


class HeadersIdentity(BaseModel):
    """Identity represented via per-actor headers (spec R4.1)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["headers"] = "headers"
    headers: dict[str, str]

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("headers identity strategy requires at least one header")
        for header_name in value:
            if not header_name or any(ord(char) < 33 or ord(char) > 126 for char in header_name):
                raise ValueError(f"identity header name {header_name!r} must be visible ASCII")
        return _validate_identity_templates(value)


class BearerIdentity(BaseModel):
    """Identity represented via a bearer token resolved from an env var (spec R4.2)."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["bearer"] = "bearer"
    header_name: StrictStr = "Authorization"
    token_env: StrictStr

    @field_validator("header_name")
    @classmethod
    def validate_header_name(cls, value: str) -> str:
        if not value or any(ord(char) < 33 or ord(char) > 126 for char in value):
            raise ValueError("bearer header_name must be visible ASCII")
        return value

    @field_validator("token_env")
    @classmethod
    def validate_token_env(cls, value: str) -> str:
        if not value:
            raise ValueError("token_env must be a non-empty environment variable name")
        return value


IdentityStrategy = Annotated[HeadersIdentity | BearerIdentity, Field(discriminator="kind")]


def resolve_identity_headers(
    strategy: IdentityStrategy | None,
    authorization: AuthorizationContext,
) -> tuple[dict[str, str], bool]:
    """Resolve the identity strategy against an authorization context.

    Returns ``(headers, represented)``. When ``strategy`` is None, returns
    ``({}, False)``. For bearer, the token is resolved from the environment;
    if the env var is unset, ``represented`` is False and no header is emitted.
    """
    if strategy is None:
        return {}, False
    if isinstance(strategy, HeadersIdentity):
        resolved = {}
        for header_name, template in strategy.headers.items():
            resolved[header_name] = _interpolate(template, authorization)
        return resolved, True
    token = os.environ.get(strategy.token_env)
    if not token:
        return {}, False
    return {strategy.header_name: f"Bearer {token}"}, True


def _interpolate(template: str, authorization: AuthorizationContext) -> str:
    """Interpolate only the allowlisted placeholders from the authorization context."""

    def _replace(match: re.Match[str]) -> str:
        placeholder = f"{{{match.group(1)}}}"
        if placeholder == "{actor_user_id}":
            return str(authorization.user_id)
        if placeholder == "{actor_tenant_id}":
            return str(authorization.tenant_id)
        if placeholder == "{actor_department_id}":
            return str(authorization.department_id) if authorization.department_id else ""
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_replace, template)


def _sentinel_auth() -> AuthorizationContext:
    """Minimal authorization context for probing identity resolution without a real actor."""
    return AuthorizationContext(
        tenant_id=UUID(int=0),
        user_id=UUID(int=0),
        department_id=None,
        classification=Classification.INTERNAL,
        allowed_user_ids=set(),
        allowed_group_ids=set(),
        is_authenticated=True,
        source="synthetic",
    )


class GenericHTTPConfig(BaseModel):
    """Validated settings loaded from ``[adapters.generic_http]``."""

    model_config = ConfigDict(extra="forbid")

    base_url: StrictStr
    retrieve_path: StrictStr
    answer_path: StrictStr | None = None
    health_path: StrictStr = "health"
    timeout_seconds: float = 10.0
    health_retries: StrictInt = 3
    health_backoff_seconds: float = 0.25
    auth_header: StrictStr | None = None
    auth_token: StrictStr | None = None
    identity: IdentityStrategy | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base_url must not contain credentials, query, or fragment")
        if any(ord(char) < 32 for char in value):
            raise ValueError("base_url must not contain control characters")
        return value.rstrip("/")

    _validate_retrieve_path = field_validator("retrieve_path")(_relative_path)
    _validate_optional_paths = field_validator("answer_path", "health_path")(
        lambda value: None if value is None else _relative_path(value)
    )

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        return value

    @field_validator("health_retries")
    @classmethod
    def validate_retries(cls, value: int) -> int:
        if not 0 <= value <= _MAX_HEALTH_RETRIES:
            raise ValueError(f"health_retries must be between 0 and {_MAX_HEALTH_RETRIES}")
        return value

    @field_validator("health_backoff_seconds")
    @classmethod
    def validate_backoff(cls, value: float) -> float:
        if not math.isfinite(value) or not 0 <= value <= _MAX_BACKOFF_SECONDS:
            raise ValueError(
                f"health_backoff_seconds must be finite and between 0 and {_MAX_BACKOFF_SECONDS}"
            )
        return value

    @field_validator("auth_header")
    @classmethod
    def validate_auth_header(cls, value: str | None) -> str | None:
        if value is not None and (
            not value or any(ord(char) < 33 or ord(char) > 126 for char in value)
        ):
            raise ValueError("auth_header must be a visible, non-empty HTTP header name")
        return value

    @field_validator("auth_token")
    @classmethod
    def validate_auth_token(cls, value: str | None) -> str | None:
        if value is not None and (not value or any(char in value for char in "\r\n")):
            raise ValueError("auth_token must be a non-empty static token without line breaks")
        return value

    @model_validator(mode="after")
    def validate_auth_pair(self) -> GenericHTTPConfig:
        if self.auth_token is not None and self.auth_header is None:
            self.auth_header = "Authorization"
        if self.auth_header is not None and self.auth_token is None:
            raise ValueError("auth_header requires auth_token")
        return self


class _HTTPResponse(Protocol):
    status: int

    def __enter__(self) -> _HTTPResponse: ...
    def __exit__(self, *args: object) -> None: ...
    def read(self) -> bytes: ...


_Opener = Callable[[Request, float], _HTTPResponse]


def _default_opener(request: Request, timeout: float) -> _HTTPResponse:
    return cast(_HTTPResponse, urlopen(request, timeout=timeout))


class GenericHTTPTransport:
    """Small synchronous JSON transport used by the generic HTTP adapter.

    Only health checks are retried.  POST operations deliberately perform one
    request so a transient response cannot duplicate a target-side operation.
    """

    def __init__(
        self,
        config: GenericHTTPConfig,
        *,
        opener: _Opener | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self._opener = opener or _default_opener
        self._sleeper = sleeper

    def post_json(
        self, path: str, payload: object, *, extra_headers: dict[str, str] | None = None
    ) -> object:
        """POST one JSON payload and decode the JSON response."""

        return self._request("POST", path, payload, decode_json=True, extra_headers=extra_headers)

    def get_json(self, path: str, *, extra_headers: dict[str, str] | None = None) -> object:
        """GET one endpoint and decode its JSON response."""

        return self._request("GET", path, None, decode_json=True, extra_headers=extra_headers)

    def health(self) -> bool:
        """Check health, retrying only transient failures within the budget."""

        attempts = self.config.health_retries + 1
        for attempt in range(attempts):
            try:
                self._request("GET", self.config.health_path, None, decode_json=False)
                return True
            except AdapterTransportError as exc:
                retryable = exc.status_code >= 500
            except AdapterError:
                retryable = True

            if not retryable or attempt == attempts - 1:
                return False
            delay = min(
                self.config.health_backoff_seconds * (2**attempt),
                60.0,
            )
            self._sleeper(delay)
        return False

    def _request(
        self,
        method: str,
        path: str,
        payload: object | None,
        *,
        decode_json: bool,
        extra_headers: dict[str, str] | None = None,
    ) -> object:
        url = self._endpoint_url(path)
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.config.auth_token is not None and self.config.auth_header is not None:
            headers[self.config.auth_header] = f"Bearer {self.config.auth_token}"
        if extra_headers:
            headers.update(extra_headers)
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with self._opener(request, self.config.timeout_seconds) as response:
                status = response.status
                raw = response.read()
        except HTTPError as exc:
            raise AdapterTransportError(method.lower(), exc.code) from None
        except (TimeoutError, OSError, URLError) as exc:
            raise AdapterError(method.lower(), "request failed") from exc

        if not 200 <= status < 300:
            raise AdapterTransportError(method.lower(), status)
        if not decode_json:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError, UnicodeError):
            raise AdapterError(method.lower(), "response body is not JSON") from None

    def _endpoint_url(self, path: str) -> str:
        """Join only a validated relative endpoint to the normalized base URL."""

        return f"{self.config.base_url}/{_relative_path(path)}"


class _AdapterTransport(Protocol):
    def post_json(
        self, path: str, payload: object, *, extra_headers: dict[str, str] | None = None
    ) -> object: ...

    def health(self) -> bool: ...


class _DecodedResponse:
    """Minimal response view consumed by the shared strict mapping helpers."""

    status_code = 200

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def json(self) -> object:
        return self._payload


class GenericHTTPAdapter:
    """RAGAdapter implementation for a configured JSON HTTP target."""

    name = "generic_http"

    def __init__(
        self,
        config: GenericHTTPConfig,
        *,
        transport: _AdapterTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or GenericHTTPTransport(config)
        self.last_identity_represented: bool = False
        self._resolved_secrets: list[str] = []

    def check_identity_represented(self) -> bool:
        """Check if identity is represented for the current config (spec R4.2).

        Returns False when no identity strategy is configured. For bearer,
        returns False when the token env var is unset.
        """
        _, represented = resolve_identity_headers(self.config.identity, _sentinel_auth())
        return represented

    def _sanitize(self, text: str) -> str:
        """Redact any resolved secrets from text before it leaves the adapter."""
        return redact_secrets(text, self._resolved_secrets)

    def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        identity_headers, identity_represented = resolve_identity_headers(
            self.config.identity, request.authorization
        )
        self.last_identity_represented = identity_represented
        self._resolved_secrets = []
        if isinstance(self.config.identity, BearerIdentity) and identity_represented:
            token = os.environ.get(self.config.identity.token_env, "")
            if token:
                self._resolved_secrets.append(token)
        try:
            payload = self.transport.post_json(
                self.config.retrieve_path,
                {"question": request.query, "top_k": request.top_k},
                extra_headers=identity_headers or None,
            )
            return map_retrieve_response(_DecodedResponse(payload))
        except AdapterTransportError as exc:
            raise AdapterTransportError(exc.operation, exc.status_code) from exc.__cause__
        except AdapterError as exc:
            sanitized_msg = self._sanitize(str(exc).split(": ", 1)[-1])
            raise AdapterError(exc.operation, sanitized_msg) from exc.__cause__

    def answer(
        self,
        request: RetrievalRequest,
        chunks: list[RetrievedChunk],
    ) -> str:
        path = require_answer_path(self.config.answer_path)
        identity_headers, identity_represented = resolve_identity_headers(
            self.config.identity, request.authorization
        )
        self.last_identity_represented = identity_represented
        self._resolved_secrets = []
        if isinstance(self.config.identity, BearerIdentity) and identity_represented:
            token = os.environ.get(self.config.identity.token_env, "")
            if token:
                self._resolved_secrets.append(token)
        try:
            payload = self.transport.post_json(
                path,
                {
                    "question": request.query,
                    "context": [chunk.model_dump(mode="json") for chunk in chunks],
                },
                extra_headers=identity_headers or None,
            )
            answer_text = map_answer_response(_DecodedResponse(payload))
            return self._sanitize(answer_text)
        except AdapterTransportError as exc:
            raise AdapterTransportError(exc.operation, exc.status_code) from exc.__cause__
        except AdapterError as exc:
            sanitized_msg = self._sanitize(str(exc).split(": ", 1)[-1])
            raise AdapterError(exc.operation, sanitized_msg) from exc.__cause__

    def is_healthy(self) -> bool:
        return self.transport.health()
