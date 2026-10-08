from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol

from jsonschema import Draft202012Validator, SchemaError, ValidationError
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    OpenAI,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
)

from sistema_incendios_forestales.api.config import RuntimeSettings


class LLMProviderError(RuntimeError):
    """Base class for explicit, safe-to-report provider failures."""

    code = "llm_provider_error"


class LLMAuthenticationError(LLMProviderError):
    code = "llm_authentication_error"


class LLMQuotaError(LLMProviderError):
    code = "llm_quota_error"


class LLMTransientError(LLMProviderError):
    code = "llm_transient_error"


class LLMRefusalError(LLMProviderError):
    code = "llm_refusal"


class LLMSchemaError(LLMProviderError):
    code = "llm_schema_error"


class LLMOutputError(LLMProviderError):
    code = "llm_invalid_output"


class LLMTokenLimitError(LLMProviderError):
    code = "llm_token_limit"


class LLMMockResponseMissingError(LLMProviderError):
    code = "llm_mock_response_missing"


@dataclass(frozen=True)
class LLMRequest:
    analysis_id: str
    role: str
    system_prompt: str
    user_prompt: str
    schema_name: str
    schema_version: str
    json_schema: Mapping[str, object]
    prompt_version: str
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class LLMResponse:
    output: Mapping[str, object]
    provider: str
    model: str
    metadata: Mapping[str, str | int | None]


class LLMProvider(Protocol):
    def complete(self, request: LLMRequest, budget: LLMRunBudget) -> LLMResponse:
        """Generate a schema-validated response without persisting prompt content."""


@dataclass(frozen=True)
class _TokenReservation:
    token_count: int


class LLMRunBudget:
    """Thread-safe output-token budget shared by every call in one analysis run."""

    def __init__(self, limit: int) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("Run token budget must be a positive integer")
        self.limit = limit
        self._used = 0
        self._reserved = 0
        self._lock = threading.Lock()

    @property
    def remaining(self) -> int:
        with self._lock:
            return self.limit - self._used - self._reserved

    def reserve(self, requested: int, remaining_attempts: int) -> _TokenReservation:
        with self._lock:
            available = self.limit - self._used - self._reserved
            token_count = min(requested, available // remaining_attempts)
            if token_count <= 0:
                raise LLMTokenLimitError("The analysis run has exhausted its output-token budget")
            self._reserved += token_count
            return _TokenReservation(token_count)

    def settle(self, reservation: _TokenReservation, used: int | None) -> None:
        with self._lock:
            self._reserved -= reservation.token_count
            charged = reservation.token_count if used is None else used
            self._used += charged


class OpenAIProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        max_output_tokens_per_run: int,
        client: object | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI API key must not be empty")
        if not model.strip():
            raise ValueError("OpenAI model must not be empty")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("OpenAI timeout must be finite and positive")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or not 0 <= max_retries <= 2:
            raise ValueError("OpenAI retries must be an integer from 0 to 2")
        if (
            isinstance(max_output_tokens_per_run, bool)
            or not isinstance(max_output_tokens_per_run, int)
            or max_output_tokens_per_run <= 0
        ):
            raise ValueError("OpenAI per-run output-token ceiling must be a positive integer")
        self.model = model
        self.max_retries = max_retries
        self.max_output_tokens_per_run = max_output_tokens_per_run
        if client is None:
            client = OpenAI(
                api_key=api_key,
                timeout=timeout_seconds,
                max_retries=0,
            )
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._sleeper = sleeper

    def complete(self, request: LLMRequest, budget: LLMRunBudget) -> LLMResponse:
        validator = _validator_for(request.json_schema)
        if budget.limit > self.max_output_tokens_per_run:
            raise LLMTokenLimitError(
                "The analysis run token budget exceeds the configured provider ceiling"
            )
        if request.max_output_tokens is not None and (
            isinstance(request.max_output_tokens, bool)
            or not isinstance(request.max_output_tokens, int)
            or request.max_output_tokens <= 0
        ):
            raise LLMTokenLimitError("Requested output tokens must be a positive integer")

        requested_tokens = min(
            request.max_output_tokens or budget.limit,
            self.max_output_tokens_per_run,
        )
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            reservation = budget.reserve(requested_tokens, attempts - attempt)
            try:
                response = self._client.chat.completions.create(  # type: ignore[attr-defined]
                    model=self.model,
                    messages=[
                        {"role": "system", "content": request.system_prompt},
                        {"role": "user", "content": request.user_prompt},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": request.schema_name,
                            "strict": True,
                            "schema": dict(request.json_schema),
                        },
                    },
                    max_completion_tokens=reservation.token_count,
                    timeout=self._timeout_seconds,
                )
            except OpenAIError as error:
                classified = _translate_openai_error(error)
                retryable = isinstance(classified, LLMTransientError)
                charge = reservation.token_count if isinstance(
                    error, (APIConnectionError, APITimeoutError, InternalServerError)
                ) else 0
                budget.settle(reservation, charge)
                if not retryable or attempt + 1 == attempts:
                    raise classified from None
                self._sleeper(min(2**attempt, 8))
                continue

            usage_tokens = _completion_tokens(response)
            budget.settle(reservation, usage_tokens)
            if usage_tokens is not None and usage_tokens > reservation.token_count:
                raise LLMTokenLimitError(
                    "OpenAI reported output usage above the reserved run-token limit"
                )
            return _parse_and_validate_response(
                response,
                validator=validator,
                request=request,
                model=self.model,
                usage_tokens=usage_tokens,
            )

        raise AssertionError("Retry loop exited without a result or provider error")


class MockLLM:
    """Explicit mock adapter; responses must be supplied by tests/development code."""

    def __init__(self, responses: Mapping[str, Mapping[str, object]]) -> None:
        self._responses = responses

    def complete(self, request: LLMRequest, budget: LLMRunBudget) -> LLMResponse:
        validator = _validator_for(request.json_schema)
        output = self._responses.get(request.schema_name)
        if output is None:
            raise LLMMockResponseMissingError(
                f"No explicit mock response is configured for schema '{request.schema_name}'"
            )
        try:
            validator.validate(output)
        except ValidationError as error:
            raise LLMOutputError(
                "Mock output does not satisfy the requested JSON Schema"
            ) from None
        reservation = budget.reserve(1, 1)
        budget.settle(reservation, 1)
        return LLMResponse(
            output=dict(output),
            provider="mock",
            model="explicit-mock",
            metadata={
                "provider": "mock",
                "model": "explicit-mock",
                "prompt_version": request.prompt_version,
                "schema_version": request.schema_version,
            },
        )


def create_llm_provider(settings: RuntimeSettings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockLLM({})
    if (
        settings.llm_provider != "openai"
        or settings.openai_api_key is None
        or settings.openai_model is None
        or settings.llm_timeout_seconds is None
        or settings.llm_max_retries is None
        or settings.llm_max_output_tokens_per_run is None
    ):
        raise LLMProviderError("The explicitly selected LLM provider is not fully configured")
    return OpenAIProvider(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        max_output_tokens_per_run=settings.llm_max_output_tokens_per_run,
    )


def _validator_for(schema: Mapping[str, object]) -> Draft202012Validator:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise LLMSchemaError("The supplied JSON Schema is invalid") from None
    return Draft202012Validator(schema)


def _parse_and_validate_response(
    response: object,
    *,
    validator: Draft202012Validator,
    request: LLMRequest,
    model: str,
    usage_tokens: int | None,
) -> LLMResponse:
    try:
        choice = response.choices[0]  # type: ignore[attr-defined]
        message = choice.message
        refusal = message.refusal
        if refusal:
            raise LLMRefusalError("The provider refused the structured-output request")
        content = message.content
        if not isinstance(content, str):
            raise LLMOutputError("The provider returned no structured content")
        output = json.loads(content)
        if not isinstance(output, dict):
            raise LLMOutputError("The provider output must be a JSON object")
        validator.validate(output)
    except LLMProviderError:
        raise
    except (IndexError, AttributeError, TypeError, json.JSONDecodeError, ValidationError) as error:
        raise LLMOutputError(
            "The provider response is invalid or does not satisfy its JSON Schema"
        ) from None

    actual_model = getattr(response, "model", None)
    request_id = getattr(response, "_request_id", None) or getattr(response, "id", None)
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", usage_tokens)
    metadata: dict[str, str | int | None] = {
        "provider": "openai",
        "model": model,
        "actual_model": actual_model if isinstance(actual_model, str) else None,
        "request_id": request_id if isinstance(request_id, str) else None,
        "prompt_version": request.prompt_version,
        "schema_name": request.schema_name,
        "schema_version": request.schema_version,
        "input_tokens": prompt_tokens if isinstance(prompt_tokens, int) else None,
        "output_tokens": completion_tokens if isinstance(completion_tokens, int) else None,
    }
    return LLMResponse(
        output=output,
        provider="openai",
        model=model,
        metadata=metadata,
    )


def _completion_tokens(response: object) -> int | None:
    usage = getattr(response, "usage", None)
    tokens = getattr(usage, "completion_tokens", None)
    return (
        tokens
        if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0
        else None
    )


def _translate_openai_error(error: OpenAIError) -> LLMProviderError:
    if isinstance(error, (AuthenticationError, PermissionDeniedError)):
        return LLMAuthenticationError("OpenAI rejected the configured credentials or permissions")
    if isinstance(error, RateLimitError) and _is_quota_error(error):
        return LLMQuotaError("The OpenAI account has exhausted its quota")
    if isinstance(error, (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)):
        return LLMTransientError("OpenAI is temporarily unavailable or the request timed out")
    if isinstance(error, (BadRequestError, APIStatusError)):
        return LLMSchemaError("OpenAI rejected the structured-output request or schema")
    return LLMProviderError(f"OpenAI request failed ({type(error).__name__})")


def _is_quota_error(error: APIStatusError) -> bool:
    body = error.body
    if not isinstance(body, Mapping):
        return False
    detail = body.get("error", body)
    if not isinstance(detail, Mapping):
        return False
    code = detail.get("code")
    error_type = detail.get("type")
    markers = {str(value).lower() for value in (code, error_type) if value is not None}
    return bool(
        markers
        & {
            "insufficient_quota",
            "quota_exceeded",
            "billing_hard_limit_reached",
            "billing_not_active",
        }
    )
