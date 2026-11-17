from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
class RuntimeConfigurationError(RuntimeError):
    """Raised when required local runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class RuntimeSettings:
    snapshot_dir: Path
    snapshot_version: str
    snapshot_manifest_sha256: str
    llm_provider: str
    audit_db_path: Path
    openai_api_key: str | None = field(default=None, repr=False)
    openai_model: str | None = None
    llm_timeout_seconds: float | None = None
    llm_max_retries: int | None = None
    llm_max_output_tokens_per_run: int | None = None


def load_settings(environ: Mapping[str, str] | None = None) -> RuntimeSettings:
    values = os.environ if environ is None else environ
    errors: list[str] = []

    snapshot_dir_value = values.get("FIREWATCH_SNAPSHOT_DIR", "").strip()
    snapshot_version = values.get("FIREWATCH_SNAPSHOT_VERSION", "").strip()
    manifest_sha256 = values.get("FIREWATCH_SNAPSHOT_MANIFEST_SHA256", "").strip()
    audit_db_value = values.get("FIREWATCH_AUDIT_DB", "").strip()

    if not snapshot_dir_value:
        errors.append("FIREWATCH_SNAPSHOT_DIR is required")
        snapshot_dir = Path()
    else:
        snapshot_dir = Path(snapshot_dir_value).expanduser().resolve()
        if not snapshot_dir.is_dir():
            errors.append(f"Snapshot directory does not exist: {snapshot_dir}")

    if not snapshot_version:
        errors.append("FIREWATCH_SNAPSHOT_VERSION is required")
    if not _SHA256_PATTERN.fullmatch(manifest_sha256):
        errors.append("FIREWATCH_SNAPSHOT_MANIFEST_SHA256 must be a 64-character SHA-256")
    audit_db_path = (
        Path(audit_db_value).expanduser().resolve()
        if audit_db_value
        else Path(__file__).resolve().parents[3] / "data" / "firewatch-audit.sqlite"
    )

    llm_provider = values.get("FIREWATCH_LLM_PROVIDER", "").strip().lower()
    openai_api_key: str | None = None
    openai_model: str | None = None
    llm_timeout: float | None = None
    llm_retries: int | None = None
    llm_max_tokens: int | None = None
    if not llm_provider:
        errors.append("FIREWATCH_LLM_PROVIDER is required and must be selected explicitly")
    if llm_provider not in {"openai", "mock"}:
        errors.append("FIREWATCH_LLM_PROVIDER must be 'openai' or explicitly 'mock'")
    elif llm_provider == "openai":
        openai_api_key = values.get("OPENAI_API_KEY", "").strip()
        if not openai_api_key:
            errors.append("OPENAI_API_KEY is required when the OpenAI provider is selected")
            openai_api_key = None
        openai_model = values.get("FIREWATCH_OPENAI_MODEL", "").strip()
        if not openai_model:
            errors.append("FIREWATCH_OPENAI_MODEL is required when the OpenAI provider is selected")

        timeout_value = values.get("FIREWATCH_LLM_TIMEOUT_SECONDS", "")
        try:
            llm_timeout = float(timeout_value)
            if not math.isfinite(llm_timeout) or llm_timeout <= 0:
                raise ValueError
        except ValueError:
            errors.append("FIREWATCH_LLM_TIMEOUT_SECONDS must be a finite positive number")
            llm_timeout = None

        retries_value = values.get("FIREWATCH_LLM_MAX_RETRIES", "")
        try:
            llm_retries = int(retries_value)
            if not 0 <= llm_retries <= 2:
                raise ValueError
        except ValueError:
            errors.append("FIREWATCH_LLM_MAX_RETRIES must be an integer from 0 to 2")
            llm_retries = None

        tokens_value = values.get("FIREWATCH_LLM_MAX_OUTPUT_TOKENS_PER_RUN", "")
        try:
            llm_max_tokens = int(tokens_value)
            if llm_max_tokens <= 0:
                raise ValueError
        except ValueError:
            errors.append("FIREWATCH_LLM_MAX_OUTPUT_TOKENS_PER_RUN must be a positive integer")
            llm_max_tokens = None

    if errors:
        raise RuntimeConfigurationError(
            "Local runtime configuration is invalid: " + "; ".join(errors)
        )

    return RuntimeSettings(
        snapshot_dir=snapshot_dir,
        snapshot_version=snapshot_version,
        snapshot_manifest_sha256=manifest_sha256.lower(),
        llm_provider=llm_provider,
        audit_db_path=audit_db_path,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        llm_timeout_seconds=llm_timeout,
        llm_max_retries=llm_retries,
        llm_max_output_tokens_per_run=llm_max_tokens,
    )
