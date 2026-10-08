from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
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


def load_settings(environ: Mapping[str, str] | None = None) -> RuntimeSettings:
    values = os.environ if environ is None else environ
    errors: list[str] = []

    snapshot_dir_value = values.get("FIREWATCH_SNAPSHOT_DIR", "").strip()
    snapshot_version = values.get("FIREWATCH_SNAPSHOT_VERSION", "").strip()
    manifest_sha256 = values.get("FIREWATCH_SNAPSHOT_MANIFEST_SHA256", "").strip()

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

    llm_provider = values.get("FIREWATCH_LLM_PROVIDER", "openai").strip().lower()
    if llm_provider not in {"openai", "mock"}:
        errors.append("FIREWATCH_LLM_PROVIDER must be 'openai' or explicitly 'mock'")
    elif llm_provider == "openai":
        if not values.get("OPENAI_API_KEY", "").strip():
            errors.append("OPENAI_API_KEY is required when the OpenAI provider is selected")
        if not values.get("FIREWATCH_OPENAI_MODEL", "").strip():
            errors.append("FIREWATCH_OPENAI_MODEL is required when the OpenAI provider is selected")

        timeout_value = values.get("FIREWATCH_LLM_TIMEOUT_SECONDS", "")
        try:
            timeout = float(timeout_value)
            if not math.isfinite(timeout) or timeout <= 0:
                raise ValueError
        except ValueError:
            errors.append("FIREWATCH_LLM_TIMEOUT_SECONDS must be a finite positive number")

        retries_value = values.get("FIREWATCH_LLM_MAX_RETRIES", "")
        try:
            retries = int(retries_value)
            if not 0 <= retries <= 2:
                raise ValueError
        except ValueError:
            errors.append("FIREWATCH_LLM_MAX_RETRIES must be an integer from 0 to 2")

        tokens_value = values.get("FIREWATCH_LLM_MAX_OUTPUT_TOKENS_PER_RUN", "")
        try:
            max_tokens = int(tokens_value)
            if max_tokens <= 0:
                raise ValueError
        except ValueError:
            errors.append("FIREWATCH_LLM_MAX_OUTPUT_TOKENS_PER_RUN must be a positive integer")

    if errors:
        raise RuntimeConfigurationError(
            "Local runtime configuration is invalid: " + "; ".join(errors)
        )

    return RuntimeSettings(
        snapshot_dir=snapshot_dir,
        snapshot_version=snapshot_version,
        snapshot_manifest_sha256=manifest_sha256.lower(),
        llm_provider=llm_provider,
    )
