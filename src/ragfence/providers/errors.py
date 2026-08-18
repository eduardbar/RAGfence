"""Typed safe errors for provider transport."""


class LLMError(RuntimeError):
    pass


class LLMHTTPError(LLMError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"provider returned HTTP {status_code}")


class LLMRateLimitError(LLMHTTPError):
    pass


class LLMTimeoutError(LLMError):
    def __init__(self) -> None:
        super().__init__("provider request timed out")


class LLMResponseTooLargeError(LLMError):
    pass
