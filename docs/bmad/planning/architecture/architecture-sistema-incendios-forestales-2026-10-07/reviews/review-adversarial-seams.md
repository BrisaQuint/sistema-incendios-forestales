# Adversarial Reviewer Gate — Architecture Seams

**Target:** `ARCHITECTURE-SPINE.md`  
**Review date:** 2026-10-07  
**Scope:** Adversarial interoperability review of adopted decisions only. No source files reviewed or changed.

## Verdict

**Changes needed before independently built units can be expected to interoperate.** The spine constrains the architecture well, but several decisions specify properties without fixing the wire/persistence contract or the authority that makes those properties consistent. The following are concrete seams: two implementations can satisfy the current wording and still disagree.

## Findings

### F-1 — SSE catch-up can lose an event at the replay/live boundary

**Severity: High**  
**Location:** AD-7, AD-9; Consistency Conventions — Identifiers and events

The spine requires persistence before emission, replay after `Last-Event-ID`, and a stable per-analysis sequence, but does not require a gap-free handoff from replay to live delivery. For example, one implementation can query persisted events after sequence N and then register its live subscriber; an event committed between those operations is in neither the query result nor the subscriber's feed. Another implementation can poll the persisted sequence continuously and deliver it. Both use persisted events and support replay, yet one live trace skips an event until a later reconnect (or indefinitely).

**Tighten:** Make the SSE `id` exactly the per-analysis sequence and define exclusive replay (`sequence > Last-Event-ID`), ordering, duplicate tolerance, and a race-free catch-up/live handoff that cannot omit a committed sequence. Specify behavior for an expired/unknown cursor after retention purge (for example, explicit reset/incomplete status rather than silent continuation).

### F-2 — MAS event taxonomy and payloads are not a shared contract

**Severity: High**  
**Location:** AD-5, AD-7, AD-8; Core records — `TRACE_EVENT`

AD-7 names required *kinds* of facts (start, terminal, reviewer decision, revision) but does not enumerate canonical event names, required payload fields, or versioning. One implementation could emit a generic `intervention.finished` with a status field; another could require distinct `intervention.completed` / `intervention.failed` events and a separate decision event. Each can expose explicit immutable event types and derive its own projection, while a separately built trace UI or audit reader cannot consume both.

**Tighten:** Adopt one versioned event schema/taxonomy shared by persistence, API/SSE, and trace projection. For each required event, fix its name, required identifiers (`analysis_id`, sequence, `intervention_id` where applicable), payload shape, and allowed values; specify forward-compatibility rules for schema evolution.

### F-3 — “Versioned” role and evidence contracts do not identify interoperable schemas

**Severity: High**  
**Location:** AD-4, AD-5, AD-6; Consistency Conventions — Evidence

The decisions require versioned `EvidenceBundle`, role-specific allowed fields, structured outputs, and evidence references, but do not select canonical schemas or define their fields. One contextualizer can return claims with `evidence_refs: string[]`; another consumer can implement references as objects containing IDs and source keys. Both are versioned, structured, and grounded in evidence, but the validator/explainer cannot reliably consume outputs produced by the other independently built unit. The same ambiguity applies to revision requests and the evidence identifier's scope/uniqueness.

**Tighten:** Name the authoritative, version-controlled schemas and versions for the bundle and each role input/output. Specify required fields, null/missing representation, evidence-reference format and resolution scope, reviewer decision/revision payload, and compatibility policy. Require producer and consumer validation against those same schemas.

### F-4 — Run state and terminal result have no declared source of truth or commit boundary

**Severity: High**  
**Location:** AD-7, AD-8; Core records — `ANALYSIS_RUN` / `TRACE_EVENT`

AD-8 defines global run states, while AD-7 makes events the source of MAS visibility; neither says whether global state is authoritative in the run row or derived from run events, nor how a terminal transition is committed with its event and result. One implementation can update `ANALYSIS_RUN.state` and persist the result before appending a terminal event; another can derive the state from an event stream. A failure between writes can leave the first reporting `completed` with no terminal trace and the second reporting `running`/incomplete for the same persisted run. This is a data-ownership inconsistency, not merely the deferred policy for restarting interrupted work.

**Tighten:** Declare the authoritative representation for run state and result availability. Define the atomic persistence boundary for each state transition, its corresponding event, and any result/provenance made visible by that transition; specify idempotent behavior if a write or process fails. Require API state/result and trace-completeness projections to agree with that authority.

## Not raised

Queue capacity, interruption recovery policy, numeric timeouts, and provider retry policy are explicitly deferred in the spine; this review does not present those acknowledged open decisions as adopted-AD violations.
