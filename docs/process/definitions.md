# Binding definitions

Source: foundation review 2026-09-07. Every term defined here is used elsewhere in this document
set as if it were precise. Until now several were not, and each undefined term silently disabled
the rule built on it.

Read this before writing any rule, schema, or gate. If a rule depends on a word that is not
defined here and not defined in the module that uses it, the rule is not enforceable and must be
fixed rather than relied upon.

## Cost classes

A stage's cost class is a **declared, machine-readable attribute of the stage definition**, not a
judgement made at the call site.

- **PAID** — the stage issues at least one billable external call, consumes render capacity above
  `RENDER_MINUTES_PAID_THRESHOLD`, or consumes human operator time. Human labour counts. Storage
  and egress count when the stage creates durable storage.
- **FREE** — everything else: local validation, schema checks, layout measurement, file moves.

Within PAID, stages declare `cost_class: MODERATE | EXPENSIVE`, where EXPENSIVE means the stage's
estimated cost exceeds `EXPENSIVE_STAGE_THRESHOLD`.

Both thresholds are single-source-of-truth config values and are currently `UNKNOWN` — they are
set once real provider costs and operator rates are measured, never guessed. Until then **every
PAID stage is treated as EXPENSIVE**, which fails closed.

Consequence: the prerequisite gate in `../costs/cost-model.md` and the declaration requirements
(`prerequisites, estimated_cost, actual_cost, failure_behavior, retry_policy, idempotency_key`)
apply to every stage declared PAID. A stage with no declared cost class is a defect.

## Production-critical data

**Production-critical** is an enumerable set, not a judgement:

> Any field that appears in the personalization manifest, the shot manifest, the performance
> track, the approval record, the consent record, or any provider-adapter argument.

The no-silent-fallback rule (CLAUDE.md §6) applies to exactly this set. Because the set is
enumerable, a lint can check it once schemas exist.

## Meaningful degradation

A metric is validated by its negative control only if a **separation criterion is declared before
the run**:

> The known-bad distribution must be separable from the known-good distribution at a stated
> margin, over N repeats, with N justified by observed variance. Record the observed overlap.
> **A metric whose known-good and known-bad distributions overlap is NOT VALIDATED.**

No universal margin or N is prescribed — both are stated per metric, in advance, and recorded
with the result. Declaring them after seeing the numbers is a defect.

For blind human review, the equivalent is reviewer discrimination: report the fraction of planted
negative controls each reviewer caught, and state in advance the floor below which that
reviewer's ratings are discarded.

## Threshold lifecycle

The rule "no invented numeric thresholds" and the requirement to build gates that need thresholds
are only compatible with an explicit bootstrap state.

- **PROVISIONAL** — derived from a named labelled set, whose size and composition are recorded.
  Marked `PROVISIONAL` in config. May be used to develop and to block obviously bad artifacts;
  may **not** be used as a production acceptance gate.
- **CALIBRATED** — the metric passed its negative control under the separation criterion above,
  automated results were compared against human review, and false positives / false negatives
  were recorded.

An uncalibrated threshold that is **not marked PROVISIONAL**, or that has no named calibration
set, is a defect. This supersedes the absolute phrasing in earlier drafts.

## Downstream

**Downstream** means *every principal other than the derivation service* — service, human, CI
job, batch process, or AI agent. Specifically included: an engineer debugging production, an
exception-queue operator, a DBA, a backup restore, an analytics export, and any LLM agent given
repository or production access.

No LLM agent may hold credentials that reach raw-photo or customer-imagery storage. Human access
requires a named break-glass procedure that emits an audit event.

## External boundary

An **external boundary crossing** is any call that leaves the raw-photo service account. This
includes hosted vision APIs used for Photo QC, third-party object storage, error-reporting and
APM services, and any vendor SDK call.

"Exactly once" is therefore stated as a counter, not an adjective: the order record carries
`raw_photo_external_calls` with a hard cap. Every crossing increments it; a cap breach fails the
order. Retries, dead-letter replays and Photo QC all count.

## Artifact classes at the photo boundary

- **RAW_PHOTO** — a photograph as supplied by the customer, or any lossless-enough transform of
  it (crop, resize, format change, thumbnail, decoded frame, cache entry).
- **DERIVED_REPRESENTATION** — the output of the single allowed derivation.

A derivative is only outside the raw-photo control set if it is **not re-identifiable to the
source photograph**. A photoreal face crop, a face embedding, or a biometric template is **not**
such a derivative: it inherits the full raw-photo control set — separate storage, separate
credentials, no generic job payloads, no logging, its own retention clock.

Whether our chosen derivative qualifies is an ADR-0001 decision, not an assumption.

## Vertical policy, capability, identity asset

- **Vertical Policy** — the object of values one audience runs the engine with
  (`../architecture/layering.md`). The engine reads it; it never contains it. First instance:
  `KIDS_POLICY`.
- **Capability** — a named Core feature that a Story Template declares and a Vertical Policy
  enables; usable only when both are true. The opposite of an empty field.
- **Identity asset** — any artifact from which a subject's identity can be recovered: canonical
  avatar, identity parameters, embeddings, templates. **High-sensitivity identity assets** are
  those re-identifiable to the source photograph (embeddings, photoreal derivatives) and inherit
  the full raw-photo control set. A persistent identity, where a policy enables it, holds
  identity assets and never raw photos.

## Modal verbs

In this document set:

- **must / required** — binding. A violation is a defect.
- **must not / forbidden** — binding prohibition.
- **not required before Phase N** — deliberately deferred, with the phase named.

The phrases **"where practical", "where appropriate", "where material", "considered",
"should ideally", "allow a field such as"** are banned. Each previously converted a rule into a
preference. Where one appears, replace it with `required`, `forbidden`, or
`not required before Phase N` — never leave it.

## Sentinels

Exactly one literal for an unknown value: **`NOT_VERIFIED`**, and **`UNKNOWN`** for a value that
is knowable but not yet measured. Defined here; every other file cites this one. `0` is never a
substitute for either, for a price or for anything else.

## Document precedence

CLAUDE.md §0 lists the priority order. Two clarifications it lacks:

- Where **CLAUDE.md and a module conflict**, CLAUDE.md wins, and the module is a defect to be
  fixed in the same change — not a competing authority.
- An **approved ADR supersedes any module text it explicitly names**, and the module must be
  updated to cite that ADR in the same commit. Without this, an ADR recording hard-won evidence
  would rank below prose written before the evidence existed.
