from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx2 as httpx
import pytest
from openai import APITimeoutError, APIConnectionError, AuthenticationError, RateLimitError

from sistema_incendios_forestales.llm import (
    LLMAuthenticationError,
    LLMMockResponseMissingError,
    LLMOutputError,
    LLMQuotaError,
    LLMRefusalError,
    LLMRequest,
    LLMRunBudget,
    LLMSchemaError,
    LLMTokenLimitError,
    LLMTransientError,
    MockLLM,
    OpenAIProvider,
)


SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}


def make_request(**overrides: Any) -> LLMRequest:
    values: dict[str, Any] = {
        "analysis_id": "analysis-1",
        "role": "contextualizer",
        "system_prompt": "internal system prompt",
        "user_prompt": "internal user prompt",
        "schema_name": "role_output",
        "schema_version": "v1",
        "json_schema": SCHEMA,
        "prompt_version": "p1",
    }
    values.update(overrides)
    return LLMRequest(**values)


def make_response(
    content: str = '{"summary":"ok"}',
    *,
    refusal: str | None = None,
    completion_tokens: int = 2,
) -> SimpleNamespace:
    return SimpleNamespace(
        id="response-1",
        _request_id="request-1",
        model="test-model-revision",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, refusal=refusal),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=7, completion_tokens=completion_tokens),
    )


class FakeClient:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self.create),
        )

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def connection_error() -> APIConnectionError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return APIConnectionError(request=request)


def timeout_error() -> APITimeoutError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return APITimeoutError(request=request)


def authentication_error() -> AuthenticationError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(401, request=request, json={"error": {"message": "denied"}})
    return AuthenticationError(
        "authentication failed",
        response=response,
        body={"error": {"type": "invalid_api_key"}},
    )


def quota_error() -> RateLimitError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(429, request=request, json={"error": {"code": "insufficient_quota"}})
    return RateLimitError(
        "quota exceeded",
        response=response,
        body={"error": {"code": "insufficient_quota"}},
    )


def provider(
    client: FakeClient,
    *,
    retries: int = 0,
    limit: int = 12,
    sleeper: list[float] | None = None,
) -> OpenAIProvider:
    return OpenAIProvider(
        api_key="not-a-real-key",
        model="test-model",
        timeout_seconds=1.5,
        max_retries=retries,
        max_output_tokens_per_run=limit,
        client=client,
        sleeper=(sleeper.append if sleeper is not None else lambda _: None),
    )


def test_openai_uses_strict_json_schema_and_returns_only_allowed_metadata() -> None:
    client = FakeClient([make_response()])
    llm = provider(client)
    budget = LLMRunBudget(12)

    result = llm.complete(make_request(), budget)

    assert result.output == {"summary": "ok"}
    assert result.provider == "openai"
    assert result.model == "test-model"
    assert result.metadata == {
        "provider": "openai",
        "model": "test-model",
        "actual_model": "test-model-revision",
        "request_id": "request-1",
        "prompt_version": "p1",
        "schema_name": "role_output",
        "schema_version": "v1",
        "input_tokens": 7,
        "output_tokens": 2,
    }
    call = client.calls[0]
    assert call["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "role_output", "strict": True, "schema": SCHEMA},
    }
    assert call["max_completion_tokens"] == 12
    assert call["timeout"] == 1.5
    assert "internal system prompt" not in repr(result.metadata)
    assert "internal user prompt" not in repr(result.metadata)
    assert "not-a-real-key" not in repr(result)
    assert budget.remaining == 10


@pytest.mark.parametrize(
    ("content", "exception"),
    [
        ("not json", LLMOutputError),
        ('{"other":"value"}', LLMOutputError),
        ("[]", LLMOutputError),
    ],
)
def test_openai_rejects_invalid_structured_output(
    content: str, exception: type[Exception]
) -> None:
    client = FakeClient([make_response(content), make_response()])

    with pytest.raises(exception):
        provider(client, retries=2).complete(make_request(), LLMRunBudget(12))
    assert len(client.calls) == 1


def test_refusal_is_typed_and_not_retried() -> None:
    client = FakeClient([make_response(refusal="cannot comply")])
    llm = provider(client, retries=2)

    with pytest.raises(LLMRefusalError):
        llm.complete(make_request(), LLMRunBudget(12))

    assert len(client.calls) == 1


def test_schema_definition_is_checked_before_calling_openai() -> None:
    client = FakeClient([make_response()])
    llm = provider(client)
    request = make_request(json_schema={"type": "not-a-json-schema-type"})

    with pytest.raises(LLMSchemaError, match="supplied JSON Schema is invalid"):
        llm.complete(request, LLMRunBudget(12))

    assert client.calls == []


def test_transient_network_failure_retries_only_up_to_the_configured_limit() -> None:
    sleeps: list[float] = []
    client = FakeClient([connection_error(), connection_error(), make_response()])
    llm = provider(client, retries=2, sleeper=sleeps)

    result = llm.complete(make_request(), LLMRunBudget(12))

    assert result.output == {"summary": "ok"}
    assert len(client.calls) == 3
    assert sleeps == [1, 2]


def test_transient_failure_after_retry_limit_is_typed() -> None:
    client = FakeClient([connection_error(), connection_error(), make_response()])
    llm = provider(client, retries=1)

    with pytest.raises(LLMTransientError):
        llm.complete(make_request(), LLMRunBudget(12))

    assert len(client.calls) == 2


def test_timeout_is_transient_and_retried_within_limit() -> None:
    sleeps: list[float] = []
    client = FakeClient([timeout_error(), make_response()])

    result = provider(client, retries=1, sleeper=sleeps).complete(
        make_request(), LLMRunBudget(12)
    )

    assert result.output == {"summary": "ok"}
    assert len(client.calls) == 2
    assert sleeps == [1]


@pytest.mark.parametrize(
    ("error_factory", "exception"),
    [
        (authentication_error, LLMAuthenticationError),
        (quota_error, LLMQuotaError),
    ],
)
def test_authentication_and_quota_errors_are_typed_without_retry(
    error_factory: Any, exception: type[Exception]
) -> None:
    client = FakeClient([error_factory(), make_response()])
    llm = provider(client, retries=2)

    with pytest.raises(exception):
        llm.complete(make_request(), LLMRunBudget(12))

    assert len(client.calls) == 1


def test_token_ceiling_is_shared_across_calls_in_one_run() -> None:
    client = FakeClient(
        [
            make_response(completion_tokens=3),
            make_response(completion_tokens=2),
        ]
    )
    llm = provider(client, limit=5)
    budget = LLMRunBudget(5)

    llm.complete(make_request(), budget)
    llm.complete(make_request(), budget)

    assert [call["max_completion_tokens"] for call in client.calls] == [5, 2]
    assert budget.remaining == 0
    with pytest.raises(LLMTokenLimitError):
        llm.complete(make_request(), budget)


def test_response_usage_above_reservation_fails_explicitly() -> None:
    llm = provider(FakeClient([make_response(completion_tokens=4)]), limit=3)

    with pytest.raises(LLMTokenLimitError):
        llm.complete(make_request(), LLMRunBudget(3))


def test_mock_requires_explicit_response_and_validates_it() -> None:
    request = make_request()
    budget = LLMRunBudget(3)

    with pytest.raises(LLMMockResponseMissingError, match="No explicit mock response"):
        MockLLM({}).complete(request, budget)

    response = MockLLM({"role_output": {"summary": "mock result"}}).complete(
        request, budget
    )
    assert response.provider == "mock"
    assert response.output == {"summary": "mock result"}
