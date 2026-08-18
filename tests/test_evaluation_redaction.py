import json
from uuid import UUID

from ragfence.evaluation.redaction import (
    REDACTION_TOKEN,
    bounded_text,
    redact_evidence,
    safe_hash,
    safe_id,
)


def test_recursive_redaction_removes_secrets_and_sensitive_fields():
    original = "Bearer abc.def, api_key=sk-test-123"
    value = {
        "authorization": "Bearer should-not-survive",
        "nested": [{"content": "raw chunk"}, {"authorization_header": "Token secret"}],
        "message": original,
    }
    redacted = redact_evidence(value)
    encoded = json.dumps(redacted, sort_keys=True)
    assert REDACTION_TOKEN in encoded
    assert "should-not-survive" not in encoded
    assert "raw chunk" not in encoded
    assert "sk-test-123" not in encoded
    assert "abc.def" not in encoded


def test_shared_redaction_covers_password_tokens_and_raw_content_formats():
    value = {
        "password": "plain-password",
        "access_token": "access-secret",
        "raw_content": "private raw content",
        "message": "PASSWORD=abc Token xyz-token password=abc",
    }

    redacted = redact_evidence(value)
    encoded = json.dumps(redacted, sort_keys=True)

    assert redacted["password"] == REDACTION_TOKEN
    assert redacted["access_token"] == REDACTION_TOKEN
    assert redacted["raw_content"] == REDACTION_TOKEN
    assert "plain-password" not in encoded
    assert "access-secret" not in encoded
    assert "private raw content" not in encoded
    assert "abc" not in encoded
    assert "xyz-token" not in encoded


def test_configured_markers_are_removed_from_bounded_text():
    result = bounded_text("prefix SECRET-MARKER suffix", max_length=40, markers=["SECRET-MARKER"])
    assert "SECRET-MARKER" not in result
    assert REDACTION_TOKEN in result


def test_text_is_bounded_with_explicit_truncation():
    result = bounded_text("abcdefghij", max_length=5)
    assert len(result) == 5
    assert result.endswith("…")


def test_safe_ids_and_hashes_are_deterministic_and_non_secret():
    identifier = UUID("11111111-1111-1111-1111-111111111111")
    assert safe_id(identifier) == str(identifier)
    assert safe_id("user@example.com") == "user@example.com"
    assert safe_hash("secret-value") == safe_hash("secret-value")
    assert len(safe_hash("secret-value")) == 64
    assert "secret-value" not in safe_hash("secret-value")
