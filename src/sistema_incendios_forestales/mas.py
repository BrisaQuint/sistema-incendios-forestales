from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import UUID, uuid4

from jsonschema import Draft202012Validator, ValidationError

from sistema_incendios_forestales.api.contracts import AnalysisResult, TraceEvent
from sistema_incendios_forestales.audit import AuditStore
from sistema_incendios_forestales.llm import (
    LLMProvider,
    LLMProviderError,
    LLMRequest,
    LLMRunBudget,
)

_SCHEMA_DIRECTORY = Path(__file__).resolve().parents[2] / "contracts" / "schemas"
_PROMPT_VERSION = "firewatch-mas-prompts.v1"
_UNAPPROVED_NUMBERS = re.compile(
    r"\d|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
    r"nineteen|twenty|cero|uno|dos|tres|cuatro|cinco|seis|siete|ocho|"
    r"nueve|diez|once|doce|trece|catorce|quince|diecis[eé]is|diecisiete|"
    r"dieciocho|diecinueve|veinte)\b",
    re.IGNORECASE,
)
_RoleOutput = dict[str, Any]
_OutputSummary = Callable[[Mapping[str, Any]], str]
_OutputEvidenceRefs = Callable[[Mapping[str, Any]], list[str]]
_OutputValidator = Callable[[Mapping[str, Any]], None]


class MASExecutionError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        provider_metadata: list[dict[str, str | int | None]] | None = None,
        affected_outputs: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.provider_metadata = list(provider_metadata or [])
        self.affected_outputs = list(affected_outputs or ["interpretation"])


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    evidence_type: str
    source_ref: str | None
    payload: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type,
            "source_ref": self.source_ref,
            "payload": dict(self.payload),
        }


class DeterministicMASOrchestrator:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        audit_store: AuditStore,
        token_budget: int,
    ) -> None:
        self._provider = provider
        self._audit_store = audit_store
        self._token_budget = token_budget
        self._provider_metadata: list[dict[str, str | int | None]] = []

    def run(self, deterministic_result: AnalysisResult) -> AnalysisResult:
        if deterministic_result.result is None or deterministic_result.result.fwi.value is None:
            raise MASExecutionError(
                "FWI_CORE_RESULT_UNAVAILABLE",
                "The MAS requires a persisted deterministic FWI result.",
            )

        analysis_id = deterministic_result.analysis_id
        evidence_records = self._deterministic_evidence(deterministic_result)
        evidence_by_id = {record.evidence_id: record for record in evidence_records}
        evidence_bundle = {
            "schema_version": "evidence-bundle.v1",
            "analysis_id": str(analysis_id),
            "evidence": [record.as_dict() for record in evidence_records],
        }
        self._validate_contract("evidence-bundle.v1.json", evidence_bundle)
        run_budget = LLMRunBudget(self._token_budget)
        review_feedback: list[str] = []
        previous_contextualization: dict[str, Any] | None = None

        for revision_number in range(2):
            contextualization, contextualization_ref, context_metadata = self._contextualize(
                analysis_id,
                evidence_bundle,
                evidence_by_id,
                run_budget,
                revision_number,
                review_feedback,
                previous_contextualization,
            )
            evidence_by_id[contextualization_ref] = EvidenceRecord(
                evidence_id=contextualization_ref,
                evidence_type="contextualization",
                source_ref=None,
                payload=contextualization,
            )
            review_bundle = self._extend_bundle(evidence_bundle, evidence_by_id)
            validation_input = {
                "schema_version": "validator-input.v1",
                "analysis_id": str(analysis_id),
                "evidence_bundle": review_bundle,
                "contextualization": contextualization,
                "review_number": revision_number + 1,
            }
            self._validate_contract("validator-input.v1.json", validation_input)
            validation, validator_intervention_id, validator_metadata = self._invoke_role(
                analysis_id=analysis_id,
                role="validator",
                task=f"Review contextualization revision {revision_number + 1}",
                input_contract="validator-input.v1.json",
                output_contract="validator-output.v1.json",
                output_schema_name="validator_output_v1",
                input_payload=validation_input,
                evidence_refs=[record.evidence_id for record in evidence_records]
                + [contextualization_ref],
                allowed_evidence=evidence_by_id,
                run_budget=run_budget,
                response_summary=lambda output: str(output["decision"]),
                response_evidence_refs=lambda _output: [
                    record.evidence_id for record in evidence_records
                ]
                + [contextualization_ref],
                post_validate=lambda output: self._validate_validation_decision(
                    analysis_id,
                    output,
                    contextualization,
                    evidence_by_id,
                ),
            )
            issue_refs = self._issue_refs(analysis_id, validation)
            self._record_review_decision(
                analysis_id,
                validator_intervention_id,
                validation,
                issue_refs,
            )

            if validation["decision"] == "approved":
                explainer_input = {
                    "schema_version": "explainer-input.v1",
                    "analysis_id": str(analysis_id),
                    "evidence_bundle": review_bundle,
                    "contextualization": contextualization,
                    "validation": validation,
                }
                self._validate_contract("explainer-input.v1.json", explainer_input)
                explanation, _explanation_ref, explainer_metadata = self._invoke_role(
                    analysis_id=analysis_id,
                    role="explainer",
                    task="Explain the validated contextualization",
                    input_contract="explainer-input.v1.json",
                    output_contract="explainer-output.v1.json",
                    output_schema_name="explainer_output_v1",
                    input_payload=explainer_input,
                    evidence_refs=[record.evidence_id for record in evidence_records]
                    + [contextualization_ref],
                    allowed_evidence=evidence_by_id,
                    run_budget=run_budget,
                    response_summary=lambda output: str(output["explanation"]),
                    response_evidence_refs=lambda output: list(output["evidence_refs"]),
                    reject_numeric_claims=True,
                )
                return deterministic_result.model_copy(
                    update={
                        "explanation": explanation["explanation"],
                        "explanation_evidence_refs": explanation["evidence_refs"],
                        "provider_metadata": [
                            context_metadata,
                            validator_metadata,
                            explainer_metadata,
                        ],
                    }
                )

            review_feedback = [
                f"{issue['issue_code']}: {issue['claim_id'] or 'context'}"
                for issue in validation["issues"]
            ]
            previous_contextualization = contextualization
            if revision_number == 1:
                raise MASExecutionError(
                    "MAS_VALIDATION_NOT_APPROVED",
                    "The validator did not approve contextualization after the one permitted revision.",
                    self._provider_metadata,
                    ["contextualization", "explanation"],
                )

        raise AssertionError("The MAS state machine exited without a terminal outcome")

    def _contextualize(
        self,
        analysis_id: UUID,
        evidence_bundle: Mapping[str, Any],
        evidence_by_id: Mapping[str, EvidenceRecord],
        run_budget: LLMRunBudget,
        revision_number: int,
        review_feedback: list[str],
        previous_contextualization: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], str, dict[str, str | int | None]]:
        contract_input = {
            "schema_version": "contextualizer-input.v1",
            "analysis_id": str(analysis_id),
            "evidence_bundle": self._extend_bundle(evidence_bundle, evidence_by_id),
            "revision_number": revision_number,
            "revision_feedback": list(review_feedback),
            "previous_contextualization": previous_contextualization,
        }
        self._validate_contract("contextualizer-input.v1.json", contract_input)
        output, intervention_id, metadata = self._invoke_role(
            analysis_id=analysis_id,
            role="contextualizer",
            task=(
                "Contextualize the deterministic daily result"
                if revision_number == 0
                else "Revise the contextualization using validator feedback"
            ),
            input_contract="contextualizer-input.v1.json",
            output_contract="contextualizer-output.v1.json",
            output_schema_name="contextualizer_output_v1",
            input_payload=contract_input,
            evidence_refs=[
                record.evidence_id for record in evidence_by_id.values()
            ],
            allowed_evidence=evidence_by_id,
            run_budget=run_budget,
            response_summary=lambda output: str(output["summary"]),
            response_evidence_refs=lambda output: self._claim_evidence_refs(output),
            reject_numeric_claims=True,
        )
        output_ref = self._output_ref(analysis_id, intervention_id)
        return output, output_ref, metadata

    def _invoke_role(
        self,
        *,
        analysis_id: UUID,
        role: str,
        task: str,
        input_contract: str,
        output_contract: str,
        output_schema_name: str,
        input_payload: Mapping[str, Any],
        evidence_refs: list[str],
        allowed_evidence: Mapping[str, EvidenceRecord],
        run_budget: LLMRunBudget,
        response_summary: _OutputSummary,
        response_evidence_refs: _OutputEvidenceRefs,
        post_validate: _OutputValidator | None = None,
        reject_numeric_claims: bool = False,
    ) -> tuple[_RoleOutput, UUID, dict[str, str | int | None]]:
        self._validate_contract(input_contract, input_payload)
        for evidence_ref in evidence_refs:
            self._require_evidence_ref(analysis_id, evidence_ref, allowed_evidence)

        intervention_id = uuid4()
        self._record_intervention_event(
            analysis_id=analysis_id,
            event_type="intervention_started",
            intervention_id=intervention_id,
            role=role,
            task=task,
            input_evidence_refs=evidence_refs,
        )
        request = LLMRequest(
            analysis_id=str(analysis_id),
            role=role,
            system_prompt=self._system_prompt(role),
            user_prompt=json.dumps(input_payload, ensure_ascii=False, sort_keys=True),
            schema_name=output_schema_name,
            schema_version=Path(output_contract).stem,
            json_schema=self._load_contract(output_contract),
            prompt_version=f"{_PROMPT_VERSION}:{role}",
        )
        try:
            response = self._provider.complete(request, run_budget)
            output: _RoleOutput = dict(response.output)
            self._validate_contract(output_contract, output)
            refs = response_evidence_refs(output)
            for evidence_ref in refs:
                self._require_evidence_ref(analysis_id, evidence_ref, allowed_evidence)
            if post_validate is not None:
                post_validate(output)
            if reject_numeric_claims:
                self._reject_numeric_claims(role, output)
        except LLMProviderError as error:
            self._record_intervention_event(
                analysis_id=analysis_id,
                event_type="intervention_failed",
                intervention_id=intervention_id,
                role=role,
                task=task,
                input_evidence_refs=evidence_refs,
                error_code=error.code,
                affected_outputs=[role],
            )
            raise MASExecutionError(
                error.code,
                f"The {role} intervention failed validation or provider execution.",
                self._provider_metadata,
                self._affected_outputs(role),
            ) from None
        except MASExecutionError as error:
            self._record_intervention_event(
                analysis_id=analysis_id,
                event_type="intervention_failed",
                intervention_id=intervention_id,
                role=role,
                task=task,
                input_evidence_refs=evidence_refs,
                error_code=error.code,
                affected_outputs=[role],
            )
            raise MASExecutionError(
                error.code,
                f"The {role} intervention failed deterministic post-validation.",
                self._provider_metadata,
                self._affected_outputs(role),
            ) from None
        except (ValidationError, ValueError, KeyError, TypeError) as error:
            self._record_intervention_event(
                analysis_id=analysis_id,
                event_type="intervention_failed",
                intervention_id=intervention_id,
                role=role,
                task=task,
                input_evidence_refs=evidence_refs,
                error_code="MAS_OUTPUT_CONTRACT_INVALID",
                affected_outputs=[role],
            )
            raise MASExecutionError(
                "MAS_OUTPUT_CONTRACT_INVALID",
                f"The {role} output did not satisfy its versioned contract.",
                self._provider_metadata,
                self._affected_outputs(role),
            ) from None

        output_ref = self._output_ref(analysis_id, intervention_id)
        self._record_intervention_event(
            analysis_id=analysis_id,
            event_type="intervention_completed",
            intervention_id=intervention_id,
            role=role,
            task=task,
            input_evidence_refs=evidence_refs,
            result_summary=response_summary(output),
            output_ref=output_ref,
            evidence_refs=refs,
        )
        metadata = {
            "role": role,
            "provider": response.provider,
            "model": response.model,
            "prompt_version": request.prompt_version,
            "schema_version": request.schema_version,
            "intervention_id": str(intervention_id),
        }
        allowed_metadata = {
            "actual_model",
            "request_id",
            "input_tokens",
            "output_tokens",
        }
        metadata.update(
            {
                key: value
                for key, value in response.metadata.items()
                if key in allowed_metadata
                and (isinstance(value, (str, int)) or value is None)
                and not isinstance(value, bool)
            }
        )
        self._provider_metadata.append(metadata)
        return output, intervention_id, metadata

    def _record_intervention_event(
        self,
        *,
        analysis_id: UUID,
        event_type: str,
        intervention_id: UUID,
        role: str,
        task: str,
        input_evidence_refs: list[str],
        result_summary: str | None = None,
        output_ref: str | None = None,
        evidence_refs: list[str] | None = None,
        error_code: str | None = None,
        affected_outputs: list[str] | None = None,
    ) -> None:
        events = self._audit_store.events(analysis_id)
        event = TraceEvent.model_validate(
            {
                "schema_version": "trace-event.v1",
                "analysis_id": analysis_id,
                "sequence": events[-1].sequence + 1,
                "event_type": event_type,
                "occurred_at": datetime.now(timezone.utc),
                "idempotency_key": f"{analysis_id}:{intervention_id}:{event_type}",
                "intervention_id": intervention_id,
                "agent_role": role,
                "task": task,
                "input_evidence_refs": input_evidence_refs,
                "result_summary": result_summary,
                "output_ref": output_ref,
                "evidence_refs": evidence_refs,
                "error_code": error_code,
                "affected_outputs": affected_outputs,
            }
        )
        self._audit_store.record_activity_event(event)

    def _record_review_decision(
        self,
        analysis_id: UUID,
        validator_intervention_id: UUID,
        validation: Mapping[str, Any],
        issue_refs: list[str],
    ) -> None:
        events = self._audit_store.events(analysis_id)
        decision = validation["decision"]
        event_type = (
            "review_approved" if decision == "approved" else "review_revision_requested"
        )
        event = TraceEvent.model_validate(
            {
                "schema_version": "trace-event.v1",
                "analysis_id": analysis_id,
                "sequence": events[-1].sequence + 1,
                "event_type": event_type,
                "occurred_at": datetime.now(timezone.utc),
                "idempotency_key": (
                    f"{analysis_id}:{validator_intervention_id}:{event_type}"
                ),
                "intervention_id": validator_intervention_id,
                "decision": decision,
                "issue_refs": issue_refs,
            }
        )
        self._audit_store.record_activity_event(event)

    def _validate_validation_decision(
        self,
        analysis_id: UUID,
        validation: Mapping[str, Any],
        contextualization: Mapping[str, Any],
        allowed_evidence: Mapping[str, EvidenceRecord],
    ) -> None:
        claim_ids = {claim["claim_id"] for claim in contextualization["claims"]}
        issues = validation["issues"]
        if validation["decision"] == "approved" and issues:
            raise MASExecutionError(
                "MAS_VALIDATOR_CONTRACT_INVALID",
                "An approved validation cannot contain unresolved issues.",
                self._provider_metadata,
            )
        if validation["decision"] == "revision_requested" and not issues:
            raise MASExecutionError(
                "MAS_VALIDATOR_CONTRACT_INVALID",
                "A requested revision must identify at least one issue.",
                self._provider_metadata,
            )
        for issue in issues:
            claim_id = issue["claim_id"]
            if claim_id is not None and claim_id not in claim_ids:
                raise MASExecutionError(
                    "MAS_INVALID_CLAIM_REFERENCE",
                    "The validator referred to a claim outside this contextualization.",
                    self._provider_metadata,
                )
            for evidence_ref in issue["evidence_refs"]:
                self._require_evidence_ref(analysis_id, evidence_ref, allowed_evidence)

    def _issue_refs(
        self, analysis_id: UUID, validation: Mapping[str, Any]
    ) -> list[str]:
        return [
            reference
            for issue in validation["issues"]
            for reference in [
                f"analysis:{analysis_id}:issue:{issue['issue_code']}:{issue['claim_id'] or 'run'}",
                *issue["evidence_refs"],
            ]
        ]

    def _deterministic_evidence(self, analysis: AnalysisResult) -> list[EvidenceRecord]:
        assert analysis.result is not None
        analysis_id = analysis.analysis_id
        scientific = analysis.result
        records: list[EvidenceRecord] = []
        for index, source_ref in enumerate(scientific.evidence_refs, start=1):
            evidence_id = f"analysis:{analysis_id}:evidence:{index:03d}"
            if ":weather_daily:" in source_ref:
                evidence_type = "weather_daily"
                payload = {
                    "weather_id": analysis.weather_id,
                    "date": analysis.date.isoformat(),
                    "fwi": scientific.fwi.model_dump(mode="json"),
                    "components": scientific.components.model_dump(mode="json"),
                    "meteorology": scientific.meteorology.model_dump(mode="json"),
                    "firms_count": scientific.firms_count.model_dump(mode="json"),
                    "firms_interpretation": scientific.firms_interpretation,
                }
            elif ":monthly_fwi_reference:" in source_ref:
                evidence_type = "monthly_fwi_reference"
                payload = {
                    "weather_id": analysis.weather_id,
                    "reference_month": scientific.reference_month,
                    "historical_reference_fwi": scientific.historical_reference_fwi.model_dump(
                        mode="json"
                    ),
                    "difference_from_reference": scientific.difference_from_reference.model_dump(
                        mode="json"
                    ),
                }
            else:
                evidence_type = "snapshot_manifest"
                payload = scientific.provenance.model_dump(mode="json")
            records.append(
                EvidenceRecord(
                    evidence_id=evidence_id,
                    evidence_type=evidence_type,
                    source_ref=source_ref,
                    payload=payload,
                )
            )
        return records

    def _extend_bundle(
        self,
        bundle: Mapping[str, Any],
        evidence_by_id: Mapping[str, EvidenceRecord],
    ) -> dict[str, Any]:
        records = list(bundle["evidence"])
        included = {record["evidence_id"] for record in records}
        records.extend(
            record.as_dict()
            for record in evidence_by_id.values()
            if record.evidence_id not in included
        )
        return {
            "schema_version": "evidence-bundle.v1",
            "analysis_id": bundle["analysis_id"],
            "evidence": records,
        }

    @staticmethod
    def _require_evidence_ref(
        analysis_id: UUID,
        evidence_ref: str,
        evidence_by_id: Mapping[str, EvidenceRecord],
    ) -> None:
        prefix = f"analysis:{analysis_id}:"
        if not evidence_ref.startswith(prefix) or evidence_ref not in evidence_by_id:
            raise MASExecutionError(
                "MAS_INVALID_EVIDENCE_REFERENCE",
                "An agent referenced evidence that is missing or outside this analysis.",
            )

    @staticmethod
    def _claim_evidence_refs(output: Mapping[str, Any]) -> list[str]:
        return list(
            dict.fromkeys(
                evidence_ref
                for claim in output["claims"]
                for evidence_ref in claim["evidence_refs"]
            )
        )

    @staticmethod
    def _reject_numeric_claims(role: str, output: Mapping[str, Any]) -> None:
        text_values: list[str] = []
        if role == "contextualizer":
            text_values.append(str(output["summary"]))
            text_values.extend(str(claim["text"]) for claim in output["claims"])
        elif role == "explainer":
            text_values.append(str(output["explanation"]))
        if any(_UNAPPROVED_NUMBERS.search(text) for text in text_values):
            raise MASExecutionError(
                "MAS_UNSUPPORTED_NUMERIC_CLAIM",
                "Agent prose must not reproduce or introduce numeric scientific claims.",
            )

    @staticmethod
    def _output_ref(analysis_id: UUID, intervention_id: UUID) -> str:
        return f"analysis:{analysis_id}:intervention:{intervention_id}:output"

    @staticmethod
    def _affected_outputs(role: str) -> list[str]:
        return {
            "contextualizer": ["contextualization", "validation", "explanation"],
            "validator": ["validation", "explanation"],
            "explainer": ["explanation"],
        }[role]

    @staticmethod
    def _system_prompt(role: str) -> str:
        shared = (
            "Usa solo el bundle de evidencia versionado proporcionado. No uses "
            "herramientas, SQL, filesystem, red ni APIs externas. No calcules, "
            "modifiques, infieras ni repitas valores científicos numéricos. Cita "
            "solo IDs de evidencia proporcionados. No incluyas razonamiento oculto."
        )
        role_instructions = {
            "contextualizer": (
                "Escribe un contexto descriptivo y conciso, separando observaciones "
                "de interpretación. Cada afirmación debe citar evidence_refs. No "
                "incluyas cantidades numéricas en el texto."
            ),
            "validator": (
                "Comprueba únicamente el respaldo factual y las referencias. Devuelve "
                "approved sin issues o revision_requested con códigos de issue y claim IDs."
            ),
            "explainer": (
                "Explica solo la contextualización aprobada y sus límites. Cita "
                "evidence_refs y no incluyas cantidades numéricas en el texto."
            ),
        }
        return f"{shared} {role_instructions[role]}"

    @classmethod
    def _validate_contract(cls, filename: str, instance: Mapping[str, Any]) -> None:
        validator = Draft202012Validator(cls._load_contract(filename))
        validator.validate(instance)

    @classmethod
    @lru_cache(maxsize=16)
    def _load_contract(cls, filename: str) -> dict[str, Any]:
        if Path(filename).name != filename or not filename.endswith(".json"):
            raise ValueError("MAS contract names must be fixed versioned schema filenames.")
        schema_path = _SCHEMA_DIRECTORY / filename
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        return cls._inline_schema_refs(schema, set())

    @classmethod
    def _inline_schema_refs(
        cls, schema: Any, resolving: set[str]
    ) -> Any:
        if isinstance(schema, list):
            return [cls._inline_schema_refs(item, resolving) for item in schema]
        if not isinstance(schema, dict):
            return schema
        reference = schema.get("$ref")
        if isinstance(reference, str) and not reference.startswith("#"):
            if reference in resolving:
                raise ValueError("Cyclic MAS schema reference.")
            referenced_schema = json.loads(
                (_SCHEMA_DIRECTORY / reference).read_text(encoding="utf-8")
            )
            return cls._inline_schema_refs(
                referenced_schema,
                resolving | {reference},
            )
        return {
            key: cls._inline_schema_refs(value, resolving)
            for key, value in schema.items()
            if key not in {"$id", "$schema", "title"}
        }
