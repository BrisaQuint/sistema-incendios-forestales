# Reviewer Gate — Architecture Spine Rubric

**Artifact:** `ARCHITECTURE-SPINE.md`  
**Review date:** 2026-10-07  
**Scope:** Documentation review only. Reconciliation checked against `ARCHITECTURE-DISCUSSION.md`, PRD, and approved UJ-1 `EXPERIENCE.md`; the existing project manifest/source layout was inspected for the brownfield check. No source files changed.

## Verdict

**Revise before ratification.** The spine addresses several genuine architectural divergence risks and is substantially reconciled with the product/UX constraints. The local-only deployment, deterministic science, one-day run identity, evidence-bounded MAS, persisted trace, explicit partial/error states, and most PRD capabilities are coherently represented. However, FR-8 has no explicit architecture owner, some architecture rules lack a stated verification mechanism, provider controls are deferred without a hard implementation gate, and the brownfield/operations decisions are not fully ratified or inventoried.

## Findings

### 1. [P1] PRD FR-8 descriptive-study results are not allocated to an architectural owner

**Where:** `Capability → Architecture Map`; compare PRD §4.3 FR-8 and §6.1.

The capability map covers FIRMS evidence and the historical reference separately, but not the optional/presented descriptive-study comparisons and denominators required by FR-8 (including the distinction between global medians and local-monthly-adjusted results). It does not say whether these are precomputed snapshot records, deterministic runtime output, or a result/provenance projection, nor which API/UI contract exposes them. Without that decision, the endpoint and persisted-result design could omit a PRD capability while appearing to cover FIRMS and FWI generally.

**Required correction:** Add an explicit FR-8 row and state its data source, computation/precomputation boundary, denominator/interpretation provenance, and result/API owner—or explicitly record a product-approved scope disposition.

### 2. [P1] OpenAI model and resource controls are deferred without a fail-closed implementation gate

**Where:** `Deferred` (exact model, parameters, timeout/retry/usage ceilings); `AD-6`; `AD-8`; discussion §7–9.

The documents say to select the model and transport limits after implementation-time testing, but do not prohibit implementing/enabling real provider calls before a model, finite timeout, bounded retries, and usage/cost ceiling have been approved. `AD-6` prevents fallback to MockLLM, but does not itself bound a real provider call. The account-specific data-control check is only required before the demonstration. This makes the deferred items potentially unsafe if “implementation-time” is interpreted as after the adapter is already live.

**Required correction:** Make real-provider execution unavailable until the model and hard limits are selected and tested; state a finite default timeout/retry/usage policy or explicitly require those values before provider integration is enabled. Keep the account/data-control verification as a release/demo gate.

### 3. [P2] Several architecture rules lack a defined conformance check

**Where:** `AD-1`, `AD-13`, `AD-14`.

Most rules are specific enough to prevent semantic drift, especially AD-2, AD-3, AD-5, AD-7, AD-8, AD-10, and AD-12. In contrast, “keep boundaries explicit” in AD-1 has no stated enforcement mechanism, while AD-13 is an overlapping dependency-direction rule without an `[ADOPTED]` status marker. AD-14’s “meaningful live updates” and “without repeatedly interrupting” are not yet observable acceptance criteria. These gaps leave the stated boundary/accessibility divergences to convention rather than a repeatable check.

**Required correction:** Mark AD-13’s status consistently; assign boundary checks (for example, import/architecture tests and frontend contract-only checks) and define testable live-announcement criteria, including which event classes are announced and how trace completeness is conveyed.

### 4. [P2] Brownfield reuse is described, but its ratification and migration seam remain implicit

**Where:** `Design Paradigm`, `Stack`, `Structural Seed`, and `Capability → Architecture Map`; discussion §2 and §6.

The proposal correctly recognizes and retains the Python scientific pipeline: the existing `pyproject.toml` requires Python `>=3.13`, `uv.lock` exists, and the repository has `src/data` scripts plus the `src/sistema_incendios_forestales` package. The spine also places the offline pipeline under `src/data` and uses it to produce the snapshot. This is a credible brownfield baseline, but it does not explicitly ratify which existing modules/contracts are preserved as-is versus wrapped, changed, or retired; the new snapshot boundary and ownership of the pipeline-to-runtime handoff are only described at a high level. The spine remains globally `draft`, and the companion discussion says it is not implementation authorization.

**Required correction:** Record the brownfield baseline as an adopted decision: identify the retained pipeline and its output contract, the adapter/snapshot seam, and any intended changes or migration work. Keep the overall authorization status distinct from the status of these ratified architectural decisions.

### 5. [P2] Deployment is decided, but the operations inventory is incomplete

**Where:** `AD-11`, `Structural Seed → Runtime and deployment`, `Deferred`, and discussion §7–9.

The local loopback deployment, snapshot readiness check, local audit retention, remote-deployment exclusion, snapshot provisioning, and process-recovery/queue questions are addressed. Other operations that this spine owns are not clearly marked decided, deferred, or open: local installation/launch and shutdown behavior, audit SQLite schema evolution/locking, and application-log retention/rotation. The map’s “local launch” capability has no launch contract, and undeclared operational assumptions can otherwise become implementation-by-default decisions.

**Required correction:** Add a compact deployment/operations decision inventory. Resolve or explicitly defer the omitted lifecycle items, with any required pre-implementation or pre-demo gate.

## Rubric results

| Criterion | Assessment |
|---|---|
| Fixes real divergence points | **Pass.** The rules target actual risk seams: deterministic science versus LLM interpretation, runtime versus offline data access, daily identity, spatial fallback/interpolation, trace truth/replay, missingness, and partial/error semantics. |
| Every AD is enforceable and prevents its stated divergence | **Partial.** Most are concrete constraints; AD-1/AD-13 lack a conformance mechanism, AD-13 is not marked adopted, and AD-14 needs testable announcement/completeness criteria. |
| Deferred is safe | **Partial.** Spatial selection, snapshot packaging, interrupted-run recovery, and remote deployment have useful guardrails. Provider execution limits need an explicit fail-closed gate before integration is enabled. |
| Current technologies are verified | **Pass for release existence; compatibility remains pending.** Exact listed releases were present in the official registries/distribution metadata checked for the review date. This verifies release existence, not a locked, jointly tested stack; the spine correctly leaves implementation locking/tests outstanding. Python `>=3.13` matches the existing project requirement. |
| Brownfield is ratified | **Partial.** Existing Python pipeline and packaging are recognized and the intended reuse direction is stated, but preservation/change boundaries and the pipeline-to-snapshot contract are not formally recorded as an adopted decision. |
| PRD capabilities covered | **Partial.** FR-1–7 and FR-9–11 have identifiable architecture, and FR-3 quality provenance is explicitly addressed. FR-8 descriptive-study results are not explicitly mapped to data/computation/API/UI ownership. |
| Every owned dimension decided/deferred/open, including deployment/operations | **Partial.** Major deployment and runtime operations choices are present; see Finding 5 for lifecycle items that still lack an explicit disposition. |

## Verification notes

- Reconciliation with UJ-1 is strong: single-surface experience, per-day analysis, no FWI aggregation, honest missing/partial/error states, real-only MAS events, trace details, and WCAG 2.2 AA are preserved. Spatial-selector implementation is safely left to UX within explicit coverage/no-fallback constraints.
- The discussion document is directionally consistent with the spine and clarifies that it is a proposal, not implementation authorization. Its quality/provenance and operations sections reinforce several spine rules, but do not resolve the findings above.
- Official release metadata checked: [FastAPI 0.142.4](https://pypi.org/pypi/fastapi/0.142.4/json), [Uvicorn 0.54.0](https://pypi.org/pypi/uvicorn/0.54.0/json), [OpenAI Python SDK 3.26.0](https://pypi.org/pypi/openai/3.26.0/json), [React 19.3.0](https://registry.npmjs.org/react/19.3.0), [React DOM 19.3.0](https://registry.npmjs.org/react-dom/19.3.0), [TypeScript 7.0.2](https://registry.npmjs.org/typescript/7.0.2), [Vite 8.3.3](https://registry.npmjs.org/vite/8.3.3), and [Node.js 24.21.0 distribution checksums](https://nodejs.org/dist/v24.21.0/SHASUMS256.txt). The implementation should still lock exact dependencies and run compatibility/build checks before adopting the proposed stack.
