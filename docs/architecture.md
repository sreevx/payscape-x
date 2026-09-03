# PAYSCAPE-X Architecture

## Current architecture (Part 9)

```
┌──────────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                     │
│   Control-center UI · dashboard, transactions, cases,     │
│   patterns, simulation lab, action center, event explorer │
│   transactions / transaction detail / events / failures  │
│   read the real backend synthetic dataset via the typed  │
│   client; transaction detail renders the reconstructed   │
│   JOURNEY, EVIDENCE, CONSISTENCY, OUTCOME, COMPOUND      │
│   FAILURE · CONSEQUENCES / IMPACT · SIMULATION LAB ·     │
│   AI DECISION (with human approval)                      │
└──────────────────────────┬───────────────────────────────┘
                           │  HTTP / JSON (typed client)
                           ▼
┌──────────────────────────────────────────────────────────┐
│                      API (FastAPI)                       │
│   /health · /api/v1/health · CORS · error handling       │
│   /api/v1/transactions · /api/v1/transactions/{id}       │
│   /api/v1/events         · /api/v1/scenarios             │
│   /api/v1/scenarios/{id} · /api/v1/journeys/{id}         │
│   /api/v1/journeys/{id}/graph · /journeys/{id}/integrity │
│   /api/v1/evidence/{id} · /api/v1/consistency/{id}       │
│   /api/v1/outcome/{id} · /api/v1/analysis/{id}           │
│   /api/v1/failures · /api/v1/failures/{id}               │
│   /api/v1/impact/{id} · /api/v1/simulations/{id}         │
│   /api/v1/simulations/{id}/run · /simulations/{id}/cmp   │
│   /api/v1/decisions/{id} · /decisions/{id}/approve       │
│   /api/v1/decisions/{id}/reject                          │
│   /api/v1/webhooks/razorpay (POST · TEST MODE)           │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│                    Services (modular)                     │
│   health · transactions · events · scenarios · journeys  │
│   evidence · consistency · outcome · analysis            │
│   failures · impact · simulation · decisions ·           │
│   razorpay_webhook · domain_context · validation         │
│   (data integrity only)                                  │
└──────────────┬───────────────────────────┬───────────────┘
               ▼                           ▼
┌──────────────────────────────┐  ┌──────────────────────────────┐
│      Ingestion pipeline      │  │   Journey reconstruction     │
│   (backend/app/ingestion)    │  │   (backend/app/journey)      │
│                              │  │                              │
│   raw payload ─┐             │  │   reconstruct(events) →      │
│   synthetic ────┼→ adapter → │  │     chronological + ingestion│
│   Razorpay ────┘   validate  │  │   analyze → integrity        │
│   webhook      → normalize → │  │   build   → journey graph    │
│   correlate → persist        │  │                              │
│                              │  │                              │
└──────────────────────────────┘  └──────────────┬───────────────┘
               │                                  │
               ▼                                  ▼
┌──────────────────────────────────────────────────────────┐
│          Evidence Engine (backend/app/evidence)          │
│   claim rules → what the records support                 │
│   strength (DIRECT/CORROBORATED/INDIRECT/MISSING/        │
│   CONTRADICTED) · gaps · contradictions                  │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│        Consistency Engine (backend/app/consistency)      │
│   16 documented rules → PASS / VIOLATION /               │
│   INSUFFICIENT_EVIDENCE / NOT_APPLICABLE →               │
│   overall_integrity (CONSISTENT/INCONSISTENT/            │
│   INSUFFICIENT_EVIDENCE)                                 │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│         Outcome Engine (backend/app/outcome)             │
│   11-rule decision hierarchy → FULFILLED / AT_RISK /     │
│   FAILED / UNVERIFIABLE · deterministic confidence ·     │
│   auditable reasons + rule trace + evidence references   │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│   Compound Failure Engine (backend/app/failures)         │
│   failure chain over promise stages · OBSERVED/DERIVED   │
│   nodes · BLOCKS/LEADS_TO/IMPACTS edges · root cause     │
│   selection · severity/classification/confidence         │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│  Consequence / Impact Engine (backend/app/impact)        │
│   OBSERVED · DERIVED · POTENTIAL consequences ·          │
│   SINGLE/MULTI_TRANSACTION scope (shared-SKU cohorts) ·  │
│   transparent impact score                               │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│      Simulation Lab Engine (backend/app/simulation)      │
│   deterministic read-only replay over doctored journey   │
│   views · interventions · SIMULATED results · impact     │
│   delta · assumptions · ranked comparison                │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│      AI Decision Agent (backend/app/decision)            │
│   structured verified context from Parts 3–7 → closed    │
│   registry action (DO_NOTHING / RECOVER_ROOT_CAUSE /     │
│   REFUND_OR_CONTAIN / HUMAN_REVIEW) · LLM or fallback    │
│   · code-validated references · deterministic confidence │
│   · audit trail + human approval — never executes        │
└──────────────────────────┬───────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────┐
│                  Database (PostgreSQL)                    │
│   merchants · customers · orders · payments · webhooks   │
│   products · inventory_records · inventory_events        │
│   fulfillments · fulfillment_events · shipments          │
│   delivery_events · customer_messages · refunds          │
│   scenario_instances · transaction_events (event backbone)│
│   decisions (Part 8 audit trail + human approval)         │
└──────────────────────────┬───────────────────────────────┘
                           ▲
┌──────────────────────────┴───────────────────────────────┐
│              Synthetic Event Pipeline                     │
│   deterministic generator (seed) → coherent journeys     │
│   → domain records + unified TransactionEvent stream     │
└──────────────────────────────────────────────────────────┘
```

**Principles**

- Frontend and backend are separate applications with clear boundaries.
- **Part 8 recommends; it never executes.** The Decision Agent picks one
  registered action over the verified Parts 3–7 facts and records it with
  a human-approval lifecycle (PENDING → APPROVED / REJECTED). Approving or
  rejecting only updates the `decisions` row — nothing in Part 8 executes
  refunds, payments, messages or any external action
  (REASON → RECOMMEND → WAIT FOR HUMAN).
- **Part 9 ingests Razorpay TEST MODE; it never transacts.** Webhook
  deliveries are signature-verified (or explicitly demo-mode), recorded
  as `Webhook` rows and passed through the exact Part 3 pipeline. No
  refund, payment or external call is ever performed — the pipeline still
  ends at AI RECOMMENDATION → HUMAN APPROVAL (records only).
- **Part 7 simulations are SIMULATED, never facts.** The Simulation Lab is
  deterministic and read-only: every intervention result is labelled
  SIMULATED, interventions that cannot act report NOT_APPLICABLE /
  NOT_EFFECTIVE / NOT_SUPPORTED, remedies never invent stock or
  substitutes, and a simulated remedy never fabricates a delivery. Results
  are scenario estimates — never predictions, guarantees or
  recommendations.
- The frontend talks to the API through one typed client
  (`frontend/lib/api-client.ts`); pages that read real data are marked
  `dynamic = "force-dynamic"` and never fail a static build.
- Business logic lives in backend services, never in React components
  (Rule 8) and never in route handlers.
- **AI reasons. CODE VERIFIES.** Parts 3–9 contain zero LLM calls, zero
  embeddings, zero AI-generated conclusions, zero outcome scoring from an
  AI, zero recommendations (the only LLM anywhere is the Part 8 Decision
  Agent's optional, validated, non-executing provider). Part 7 adds the
  intentional exception to "zero simulations": the Simulation Lab is
  fully deterministic and read-only, and every result is labelled
  SIMULATED. Part 8 adds the intentional exception to "zero AI": the
  Decision Agent may reason over the verified facts with an LLM, but it
  may only pick a registered action, every claim it makes is validated
  against the verified context by code (invalid output → deterministic
  fallback), its confidence is computed deterministically (an LLM
  confidence is an explanation signal only), and it never executes
  anything. Part 9 adds the intentional exception to "no provider
  integration": Razorpay TEST-MODE webhooks are accepted, verified and
  ingested — never used to perform real financial transactions, and
  DEMO / SYNTHETIC data is always clearly separated from verified
  TEST-MODE deliveries. Every ingestion, normalization, correlation,
  reconstruction, graph, integrity, evidence, consistency, outcome,
  compound-failure, impact and simulation decision is deterministic and
  explainable (`rule_id` + reason on every finding).
- Reconstruction describes what happened. It never decides what should have
  happened: missing, duplicate, delayed, contradictory, out-of-order,
  unknown and orphan events are preserved exactly as recorded.
- **The Outcome Engine verifies the current business outcome from
  records.** FULFILLED is only assigned when the goods were delivered; a
  successful payment is never FULFILLED on its own. Contradictory or
  insufficient records produce UNVERIFIABLE, never a guess.
- **Part 6 describes failures; it does not predict.** Consequences are
  strictly labelled OBSERVED (records), DERIVED (deterministic steps) or
  POTENTIAL (signalled possibilities — explicitly NOT predictions and
  never rendered as facts). A compound failure is only asserted over a
  FAILED outcome with a genuine multi-stage chain; missing or
  contradictory records never produce an invented causal chain.
- **Cross-transaction impact requires an explicit shared identifier.** The
  impact engine only links transactions that share a product SKU on their
  `INVENTORY_OUT_OF_STOCK` records — relationships are never inferred by
  fuzzy matching or by guessing that the same condition "probably" hit
  another order.
- All configuration comes from environment variables; no secrets are
  hardcoded or exposed.

## The journey data model

A payment is **not** an isolated object. The core unit of analysis is the
**Business Transaction Journey**:

```
Merchant
   ↓
Customer
   ↓
Order
   ↓
Payment
   ↓
Webhook
   ↓
TransactionEvent     ← the unified chronological event backbone
   ↓
Inventory
   ↓
Fulfillment
   ↓
Shipment
   ↓
Delivery
   ↓
Customer Message
```

Every unified `TransactionEvent` carries:

- `order_id` — which business order the event belongs to (always set)
- `payment_id` — set when the event concerns a payment (null otherwise)
- `event_type` / `source` — centralised registry (`app/core/events.py`),
  never scattered strings
- `timestamp` — the business timeline
- `correlation_id` — one id per journey, shared by every event of it
- `idempotency_key` — provider/webhook identity (duplicate detection)
- `ingestion_sequence` — monotonic insertion order (Part 3), independent
  of timestamps so out-of-order ingestion is detectable
- `payload` — free-form structured context (JSON / JSONB)

```
All events
      ↓
Correlation ID
      ↓
Transaction Journey
```

`correlation_id` connects payment → webhook → order → inventory →
fulfillment → shipment → delivery → customer message → refund for a single
business transaction, so the reconstruction layer retrieves:

```
transaction
    ↓
all related events
    ↓
chronological timeline   (timestamps)
    ↓
ingestion order          (ingestion_sequence — may differ!)
    ↓
business context
```

## Part 3 — Event ingestion

`backend/app/ingestion/` accepts events from existing synthetic
TransactionEvents and from future provider/webhook payloads through one
deterministic pipeline:

```
raw payload
   → adapter        (provider-specific translation → CanonicalEvent)
   → validate       (structural checks only — rejects malformed input with errors)
   → normalize      (map event type/source onto the Part 2 registry)
   → correlate      (documented priority order)
   → idempotency    (same key + correlation → DUPLICATE, nothing written)
   → persist        (into the unified TransactionEvent stream)
```

Contract guarantees:

- **Deterministic** — same input + same database state → same outcome.
- **Idempotent** — re-ingesting an event with the same `idempotency_key`
  returns a DUPLICATE result and writes nothing.
- **Never silent** — every input produces an explicit
  `IngestionResult` (`PERSISTED` / `DUPLICATE` / `ORPHAN` / `UNKNOWN` /
  `REJECTED`) with a message.
- **Zero AI** — no classification, no scoring, no autonomous decisions.

Adapters (`app/ingestion/adapters/`): `EventAdapter` is the interface;
`RawEventAdapter` handles generic dict payloads (future webhooks);
`SyntheticAdapter` carries existing TransactionEvent rows into the pipeline
unchanged. Real providers plug in by implementing one adapter — nothing
else changes.

## Part 3 — Normalization

One centralized registry (`app/core/events.py`), one translator
(`app/ingestion/normalizer.py`). Provider spellings map deterministically:

```
payment.captured / payment_captured / PAYMENT_CAPTURED → PAYMENT_CAPTURED
webhook.received / webhook_received / WEBHOOK_RECEIVED → WEBHOOK_RECEIVED
delivery.completed / delivered → DELIVERY_COMPLETED
… (full alias table in normalizer.py)
```

Events whose type/source is not in the registry are **preserved and marked
UNKNOWN** — never deleted, never silently dropped, never auto-classified.

## Part 3 — Correlation priority

`app/journey/correlation.py` — deterministic, documented, never fuzzy:

```
1. explicit correlation_id on the event
2. order_id   → correlation of the order's existing journey events
3. payment_id → correlation of the payment's existing journey events
4. provider identifiers in the payload (provider_payment_id) → payment → journey
5. other explicit foreign keys / domain relationships (same pattern)
```

If no identity resolves, the event is preserved as an **orphan** — never
guessed, never silently discarded.

## Part 3 — Journey reconstruction

`app/journey/reconstructor.py` replays one transaction's unified events
into a canonical journey:

- `chronological_events` — sorted by (timestamp, id); timestamps are never
  mutated.
- `ingestion_events` — sorted by `ingestion_sequence` (the authoritative
  insertion order); may differ from chronological order.
- primary `correlation_id` — the most common correlation among the events
  (deterministic tiebreak); strays are preserved as orphans.

The engine does **not** assume the happy path: missing, duplicate, delayed,
contradictory, out-of-order, unrelated and unknown events all survive.

## Part 3 — Journey graph

`app/journey/graph.py` builds a deterministic graph — nodes at fixed
positions, edges derived from explicit rules (`rule_id` + human-readable
`reason`):

| Relationship   | Meaning |
|---|---|
| `PRECEDES`        | consecutive events in chronological order |
| `TRIGGERS`        | documented event-type transitions that actually occurred |
| `BELONGS_TO`      | every event → the JOURNEY root |
| `CORRELATES_WITH` | every event → the CORRELATION root |
| `DERIVED_FROM`    | identity-derived (duplicate webhook, received↔sent, refund completion, delivery return) |

Layout is `deterministic_linear`: node positions are computed purely from
order, so the JSON graph is reproducible across repeated runs and rendered
by the frontend without a graph library.

## Part 3 — Integrity detection (structural only)

`app/journey/integrity.py` reports what the stream contains — never what
the outcome should be:

- **duplicates** — same `idempotency_key` twice (earliest is canonical,
  later events flagged `is_duplicate` and kept); webhook rows delivered
  twice with the same `provider_event_id`
- **missing-event candidates** — structural rules ("if X present and Y
  absent, Y is a candidate"), e.g. `PAYMENT_CAPTURED` without
  `WEBHOOK_RECEIVED` → candidate `WEBHOOK_RECEIVED`
- **contradictions** — mutually exclusive states both present
  (capture + failure, delivered + failed, refund completed without
  initiation). Recorded with rule id, involved event ids and timestamps;
  neither event is deleted, neither is chosen
- **out-of-order** — `ingestion_sequence` order ≠ timestamp order (no
  timestamps mutated)
- **delayed** — `WEBHOOK_DELAYED` events and webhook rows flagged DELAYED
- **unknown / orphan** — outside the registry / outside the journey
  correlation, preserved

The integrity report also exposes totals (`total_events`, `linked_events`,
`first_event_at`, `last_event_at`, `duration_seconds`).

## Part 4 — Evidence Engine

`backend/app/evidence/` answers one question:

> **What do we actually have evidence for?**

It never answers *"did the business transaction succeed?"* — that is the
Outcome Engine's question.

The collector (`collector.py`) turns a reconstructed journey + the payment's
existing domain records (loaded once by `services/domain_context.py` from
the Part 2 tables — no new tables) into an `EvidenceReport`:

- **Claim rules** — 21 explicit claims ("Payment was captured", "Webhook
  delivery was delayed", "Delivery was returned", …), each bound to the
  centralized event registry. No free-form explanations.
- **Evidence categories** — PAYMENT, ORDER, WEBHOOK, INVENTORY,
  FULFILLMENT, SHIPMENT, DELIVERY, REFUND, CUSTOMER_MESSAGE, TIMING,
  CORRELATION.
- **Source traceability** — every item lists the exact `event_ids` (and
  corroborating record ids) that support its claim.

### Evidence strength (deterministic)

`app/evidence/strength.py` resolves strength purely from the records:

| Strength      | Meaning                                                        | Confidence |
|---------------|----------------------------------------------------------------|------------|
| `DIRECT`      | the claiming event is present in the journey                   | 1.0        |
| `CORROBORATED`| present AND an independent record agrees (payment row, webhook, shipment, refund …) | 1.0 |
| `INDIRECT`    | inferred only from a related record (no direct event)          | 0.5        |
| `MISSING`     | structurally expected but not observed (an evidence gap)       | 0.0        |
| `CONTRADICTED`| the claim's events exist but conflict with other recorded events | 0.5      |

Examples:

- `PAYMENT_CAPTURED` event + `payments.status = CAPTURED` → CORROBORATED.
- `PAYMENT_CAPTURED` + `PAYMENT_FAILED` both recorded → CONTRADICTED (both
  preserved).
- No `DELIVERY_COMPLETED` after shipment → MISSING delivery evidence.
- Claims the engine has no event for and no structural expectation are not
  reported — the engine never infers facts the records don't support.

Evidence gaps are structural observations ("X present but Y not observed"),
never business verdicts; Part 3 contradictions are preserved on the report
with a deterministic severity and never resolved.

## Part 4 — Consistency Engine

`backend/app/consistency/` answers one question:

> **Do the observed records agree with each other?**

`rules.py` is an explicit registry of 16 documented rules (amount matching,
lifecycle ordering, refund/delivery linkage, webhook references, …) with
severity and a deterministic evaluation function.

| Status | Meaning |
|---|---|
| `PASS` | the rule's evidence exists and agrees |
| `VIOLATION` | the rule's evidence exists and disagrees |
| `INSUFFICIENT_EVIDENCE` | the rule plausibly applies but key records are absent |
| `NOT_APPLICABLE` | the rule does not apply to this journey |

**A missing event is NOT automatically a violation.** Absence of evidence
is never turned into evidence of failure. `overall_integrity` is
CONSISTENT / INCONSISTENT / INSUFFICIENT_EVIDENCE — record agreement only,
never a business outcome.

## Part 5 — Outcome Engine

`backend/app/outcome/` answers the product's core question:

> **Did the business transaction actually succeed?**

That is deliberately NOT the same as "was the payment successful?" The
engine classifies every reconstructed transaction into exactly one of:

| Outcome | Meaning |
|---|---|
| `FULFILLED` | sufficient positive evidence that the promised transaction completed (the goods were delivered) |
| `AT_RISK` | still potentially recoverable, but evidence of a problem threatens completion |
| `FAILED` | strong deterministic evidence the transaction cannot or did not complete |
| `UNVERIFIABLE` | records insufficient or contradictory to determine the outcome |

The engine consumes the Part 3 journey, the Part 4 evidence report and the
Part 4 consistency report (`app/outcome/engine.py`, `rules.py`) and is
fully deterministic: same database state → same outcome, confidence,
reasons and references.

### Outcome rule hierarchy (explicit, documented)

Rules run in fixed priority order; the first match decides the primary
outcome, later matches that agree add corroborating reasons (compound
chains surface every failure branch), and later matches with a different
outcome are recorded in the trace as overridden. The hierarchy (documented
in `rules.py`):

```
 10  CRITICAL_CONTRADICTION            → UNVERIFIABLE
     conflicting critical records (payment captured+failed, delivered+
     failed) block certainty — unless a DELIVERY_COMPLETED strictly after
     every DELIVERY_FAILED resolves the delivery contradiction
 20  PAYMENT_FAILED_TERMINAL           → FAILED        (business did not proceed)
 30  PAYMENT_UNRESOLVED                → UNVERIFIABLE  (payment state unknown)
 40  DELIVERY_FAILED_TERMINAL          → FAILED        (definitive delivery failure)
 50  BUSINESS_FAILURE_MARKERS          → FAILED        (ORDER_NOT_CONFIRMED /
     NO_FULFILLMENT / FULFILLMENT_FAILED — explicit SYSTEM failure records)
 60  INVENTORY_ALLOCATION_FAILED       → FAILED        (OUT_OF_STOCK, no recovery)
 70  ORDER_CANCELLED_POST_CAPTURE      → FAILED        (transaction reversed)
 80  TRANSACTION_FULFILLED             → FULFILLED     (DELIVERY_COMPLETED)
 90  DELIVERY_PENDING_RISK             → AT_RISK       (shipment, no resolution)
100  FULFILLMENT_PENDING_RISK          → AT_RISK       (created, not shipped)
110  INSUFFICIENT_DOWNSTREAM_EVIDENCE  → UNVERIFIABLE  (nothing downstream)
```

Key semantics:

- **FULFILLED requires a delivery-completed record.** A captured payment
  with no delivery evidence is never FULFILLED.
- **Business failure ≠ payment failure.** In the compound-failure scenario
  the payment is captured (webhook received) yet the order is never
  confirmed, the reservation expires, inventory is out of stock and no
  fulfillment exists → **FAILED** with reasons `ORDER_NOT_CONFIRMED` and
  `INVENTORY_ALLOCATION_FAILED`. The engine never says "payment successful
  → FULFILLED".
- **UNVERIFIABLE, not FAILED, for missing evidence.** If the records cannot
  establish what happened (e.g. payment captured but no downstream
  lifecycle observed, or contradictory critical records), the engine
  returns UNVERIFIABLE — absence of evidence is never treated as business
  failure, and contradictions never produce unjustified certainty.
- Duplicates (e.g. a duplicated webhook) never change the outcome; the
  business state decides.
- A refund is recorded as part of the reason for a cancelled order — the
  outcome itself comes from the business state (cancelled, not delivered).

### Confidence methodology (deterministic)

Confidence is a **record-strength score**, not an ML probability and not
fake certainty:

```
base = 0.97 FULFILLED · 0.95 FAILED · 0.60 AT_RISK · 0.45 UNVERIFIABLE
       (UNVERIFIABLE caused by contradiction uses 0.35)
then each traced adjustment is subtracted when its signal exists:
       DELAYED_WEBHOOK       (integrity delayed events)        −0.05
       OUT_OF_ORDER_EVENTS   (ingestion order ≠ chronology)    −0.05
       CONTRADICTED_EVIDENCE (per contradicted evidence item)  −0.10
       CONSISTENCY_VIOLATION (per consistency violation)       −0.10
       (the last two apply only to non-UNVERIFIABLE outcomes —
        the UNVERIFIABLE base already reflects the weak records)
confidence = clamp(base + adjustments, 0.05, 0.99), rounded to 2dp
```

Every adjustment is returned in `confidence_adjustments` with a
`signal` + `note`, so the score is fully auditable. Examples from the
seeded dataset: NORMAL_SUCCESS 0.97; DELAYED_WEBHOOK 0.92 (delayed flag);
COMPOUND_FAILURE 0.90 (delayed webhook in the chain); MISSING_EVENT 0.45;
CONTRADICTORY_EVENT 0.35.

### Evidence completeness

`evidence_completeness` (0..1, or null when the payment was never
captured) is the fraction of the five post-payment lifecycle groups —
confirmation, inventory allocation, fulfillment, shipment, delivery — that
carry any observed record (positive or explicit-negative). It is a
descriptive metric shown alongside the outcome, not part of the
classification.

### Reasons and traceability

Every outcome returns:

- `primary_reason` and corroborating `reasons` — each with `code`,
  `message` (concise facts from records, never chain-of-thought),
  `severity`, `rule_id`, and the exact `event_ids` + `evidence_ids` that
  support it;
- `supporting_evidence_ids` / `supporting_event_ids` — the aggregate
  supporting records;
- `blocking_evidence_ids` — contradicted / missing evidence that blocks a
  definitive classification;
- `consistency_status` and `evidence_completeness`;
- `rule_trace` — every rule in priority order with `applied` + note;
- `confidence_adjustments` — every confidence delta with its reason.

## Part 6 — Compound Failure Engine

`backend/app/failures/` answers one question about a FAILED transaction:

> **What sequence of related failures caused this business outcome?**

It consumes the Part 3 journey + integrity, the Part 4 evidence and
consistency reports and the Part 5 outcome — it never recomputes the
outcome and never predicts the future. Every node, edge and root cause is
traceable to event ids / evidence ids and to the deterministic rule that
produced it.

### Compound failure semantics (when a failure is "compound")

The engine reports `detected = true` only when BOTH hold:

1. the Part 5 outcome is **FAILED**, and
2. the journey contains at least **two chain nodes spanning at least two
   distinct promise stages** (PAYMENT → WEBHOOK → ORDER → INVENTORY →
   FULFILLMENT → SHIPMENT → DELIVERY → CUSTOMER → REFUND).

Consequences of that rule:

- A lone `PAYMENT_FAILED` (or a lone order cancellation) is a
  **single-stage business failure** — reported as not detected with reason
  `SINGLE_STAGE_BUSINESS_FAILURE` (severity MEDIUM) and its records
  surfaced through the impact endpoint.
- FULFILLED / AT_RISK / UNVERIFIABLE journeys are reported not detected
  with explicit reason codes — a duplicate webhook alone is never a
  compound failure, missing evidence never invents a chain, and
  contradictory records preserve uncertainty (`OUTCOME_UNVERIFIABLE_NO_CHAIN`).
- The engine never "repairs" history and never resolves contradictions.

### Failure-chain construction

Nodes are created from the recorded event stream (`app/failures/rules.py`):

| Status | Meaning |
|---|---|
| `OBSERVED` | an event in the journey states the problem directly (e.g. `INVENTORY_OUT_OF_STOCK`, `NO_FULFILLMENT`, `CUSTOMER_COMPLAINT`) |
| `DERIVED` | follows from a documented absence only (e.g. fulfillment shipped but no shipment/delivery record ever appears → `SHIPMENT_NOT_CREATED`) |

Node kinds include PAYMENT_FAILED, WEBHOOK_DELAYED,
ORDER_NOT_CONFIRMED, ORDER_CANCELLED_AFTER_CAPTURE (only when the capture
happened — a cancellation that merely follows a payment failure is a
consequence, not a chain node), INVENTORY_RESERVATION_EXPIRED,
INVENTORY_ALLOCATION_FAILED, FULFILLMENT_FAILED, FULFILLMENT_NOT_CREATED,
SHIPMENT_NOT_CREATED (DERIVED only), DELIVERY_FAILED, DELIVERY_RETURNED and
CUSTOMER_IMPACT (complaints, or messages about a problem — routine
enquiries/confirmations are excluded).

Nodes are ordered along the promise-chain axis first, then by earliest
evidence timestamp, so the chain reads as a narrative. Consecutive nodes
are connected by `CHAIN_RULES` — a static registry that picks the
relationship from the two node kinds involved:

| Rule | Relationship |
|---|---|
| WEBHOOK_DELAY_LEADS_TO_ORDER_FAILURE | LEADS_TO |
| ORDER_FAILURE_LEADS_TO_INVENTORY_FAILURE | LEADS_TO |
| INVENTORY_EXPIRY_LEADS_TO_ALLOCATION_FAILURE | LEADS_TO |
| INVENTORY_FAILURE_BLOCKS_FULFILLMENT | BLOCKS |
| FULFILLMENT_FAILURE_BLOCKS_SHIPMENT | BLOCKS |
| DELIVERY_FAILURE_LEADS_TO_RETURN | LEADS_TO |
| SHIPMENT_FAILURE_IMPACTS_DELIVERY / DELIVERY_FAILURE_IMPACTS_CUSTOMER / FULFILLMENT_FAILURE_IMPACTS_CUSTOMER / ORDER_FAILURE_IMPACTS_CUSTOMER | PREVENTS / IMPACTS |

Edges carry `edge_id`, `relationship_type`, `rule_id` and a human-readable
`reason` — the relationship vocabulary is CAUSES / BLOCKS / LEADS_TO /
PREVENTS / IMPACTS and is never LLM-invented.

### Root-cause selection (deterministic)

`app/failures/engine.py` selects the root cause from an explicit priority
table over the OBSERVED business-stage chain nodes:

```
PAYMENT_FAILED (10)  >  INVENTORY_ALLOCATION_FAILED /
INVENTORY_RESERVATION_EXPIRED (9)  >  FULFILLMENT_NOT_CREATED /
FULFILLMENT_FAILED (8)  >  DELIVERY_FAILED (7)  >  ORDER_NOT_CONFIRMED (6)
>  ORDER_CANCELLED_AFTER_CAPTURE (5)  >  WEBHOOK_DELAYED (4)
```

Impact/derived nodes are never roots; ties resolve toward the node further
down the chain (the final blocking state — e.g. the out-of-stock
allocation rather than the earlier reservation expiry). Critically, **the
earliest event is not automatically the root cause**: in the compound
scenario the webhook delay is chronologically first yet the root cause is
`INVENTORY_ALLOCATION_FAILED` — the webhook delay is a contributing factor
in the chain, not the root.

### Severity, classification, confidence

- **Severity** uses a severity ladder (LOW < MEDIUM < HIGH < CRITICAL — not
alphabetical string ordering): max severity of the involved stages,
raised to CRITICAL at ≥ 4 distinct stages, or ≥ 3 stages with a customer
complaint. Observed results: compound failure CRITICAL;
inventory/delivery failures HIGH; single-stage failures MEDIUM;
non-FAILED journeys LOW.
- **Classification** is OBSERVED when every chain node is an observed
record, DERIVED otherwise.
- **Confidence** = the Part 5 outcome confidence (× 0.9 when the chain
contains a DERIVED node).
- Deterministic ids: `compound_failure_id` / `node_id` / `edge_id` /
`root_cause_id` are uuid5 over the transaction id (and kind), so repeated
runs and separate processes produce identical output.

### Compound failure model (API shape)

`compound_failure_id · transaction_id · detected · reason · severity ·
classification · primary_failure · failure_chain[ ] (node_id, kind, stage,
label, status OBSERVED/DERIVED, message, event_ids, evidence_ids,
timestamp, rule_id, metadata) · edges[ ] (source_node, target_node,
relationship_type, rule_id, reason) · root_causes[ ] · confidence ·
event_ids · evidence_ids · metadata (outcome + outcome_reason_code +
distinct_stages + chain_rule_ids)`.

## Part 6 — Consequence / Impact Engine

`backend/app/impact/` answers one question:

> **What are the downstream consequences of the detected failure?**

It consumes the full pipeline plus the compound-failure result and
(optionally) pre-loaded cross-transaction facts. It only emits
consequences when the Part 5 outcome is **FAILED** — for FULFILLED /
UNVERIFIABLE transactions nothing downstream is asserted.

### OBSERVED vs DERIVED vs POTENTIAL (never confused)

The same three labels used by the failure engine are applied to
consequences, and the API/UI keep them strictly separate:

| Label | Meaning | Example |
|---|---|---|
| `OBSERVED` | stated by a record in the journey | "Delivery failed", "A refund was completed", "The customer filed a complaint" |
| `DERIVED` | follows deterministically from records | "Fulfillment could not proceed — inventory allocation had failed", "A shipment could not be created — no fulfillment existed", "The captured amount was returned to the customer" |
| `POTENTIAL` | a possible future state signalled by records (a complaint or problem-contact with **no refund recorded**) | "Refund or dispute risk — the customer signalled a problem and no refund has been recorded yet" |

**POTENTIAL consequences are NOT predictions and are never presented as
facts.** They only appear when a customer signal exists (complaint or
problem message), and they are visually distinct in the UI with an explicit
"Possible future state signalled by the records — not an observed fact"
note. In the seeded data, INVENTORY_FAILURE (no customer signal) has no
potential consequences; DELIVERY_FAILURE and COMPOUND_FAILURE (customer
contact) each have exactly one.

Consequence categories: PAYMENT · ORDER · INVENTORY · FULFILLMENT ·
SHIPMENT · DELIVERY · CUSTOMER · REFUND · REVENUE · OPERATIONAL. Every
item carries `consequence_id` (uuid5), `category`, `claim`,
`classification`, `rule_id`, `event_ids`, `evidence_ids` and metadata.

### Cross-transaction impact (deterministic, identifier-only)

`app/services/impact_service.py` loads the cohort from explicit shared
identifiers — nothing fuzzy:

```
shortage SKUs of this transaction (payload product_sku on its
  INVENTORY_OUT_OF_STOCK records)
   → other payments with INVENTORY_OUT_OF_STOCK on the same SKUs
   → each member's Part 5 outcome computed deterministically
```

The impact summary then reports `scope = MULTI_TRANSACTION` when the
cohort is non-empty (else SINGLE_TRANSACTION), `affected_transactions` /
`affected_orders` (cohort including the subject transaction),
`affected_products` (distinct SKUs), `shared_skus`,
`shared_failure_patterns` (`INVENTORY_OUT_OF_STOCK`) and the `affected[ ]`
list — each member with transaction/order ids, scenario, its own Part 5
outcome, product SKUs and impact evidence label (`OBSERVED` when its own
record stream shows the shortage). In the seed-42 dataset, 15 of the 25
detected compound failures are MULTI_TRANSACTION, sharing the zero-stock
SKUs NC-0006 / NC-0013 / NC-0021 with cohorts of 4–6 FAILED transactions.
The impact engine never invents cross-transaction relationships for
delivery/order-level problems that have no shared identifier in the
records.

### Impact severity and score (transparent formula)

Severity is the compound-failure severity when detected, MEDIUM for a
single-stage FAILED transaction, and is raised one notch when the scope is
MULTI_TRANSACTION (MEDIUM→HIGH→CRITICAL). The **impact score** is a
0–100 deterministic index, returned component-by-component in
`score_components`:

```
score = min(100, severity_base + Σ observed + Σ derived + Σ potential + multi)

severity_base:  CRITICAL 60 · HIGH 45 · MEDIUM 25 · LOW 5

observed weight by consequence category:
  PAYMENT 4 · ORDER 8 · INVENTORY 8 · FULFILLMENT 8 · SHIPMENT 8 ·
  DELIVERY 8 · CUSTOMER 10 · REFUND 15 · REVENUE 5 · OPERATIONAL 4

derived weight    = max(2, observed/2)      # a derived step is weaker than a record
potential weight  = 3 each                  # signalled possibility, heavily discounted
multi_transaction = min(20, 5 × additional affected transactions)
```

Worked examples from the seeded dataset (engine-level, no cohort):
PAYMENT_FAILED 37.0 (MEDIUM base + payment + cancelled order),
REFUND_FLOW 75.5, INVENTORY_FAILURE 73.0, DELIVERY_FAILURE 83.0,
COMPOUND_FAILURE 100.0 (service-level multi-transaction result). The score
is **not** a financial-loss estimate and **not** a prediction — it is an
indexed summary of record-backed severity and consequence depth.

## The Part 5 + Part 6 pipeline (single deterministic pass)

`GET /api/v1/analysis/{id}` composes everything in one pipeline with the
journey reconstructed exactly once:

```
journey     = reconstruct(transaction)            # Part 3
evidence    = collect(journey, integrity, ctx)    # Part 4
consistency = evaluate(journey, ctx)              # Part 4
outcome     = decide(journey, integrity, evidence, consistency)          # Part 5
failure     = analyze_failure(journey, integrity, evidence, consistency,
                              outcome)                                    # Part 6
impact      = analyze_impact(journey, integrity, evidence, consistency,
                             outcome, failure, cross_transaction_view)    # Part 6
```

The response adds `compound_failure` and `impact` to the existing journey /
evidence / consistency / outcome fields (nothing removed or renamed — the
Part 4/5 sections stay byte-identical to the dedicated endpoints). No LLM.
No external APIs. No randomness. Same input → byte-equivalent JSON after
normalization. Parts 4–9 add **no database tables and no migrations** —
everything is computed from the existing Part 2/3 records (including the
Part 2 `webhooks` table, which records raw Razorpay TEST-MODE deliveries).
The Simulation Lab (Part 7), the Decision Agent (Part 8) and the Razorpay
webhook adapter (Part 9) are separate layers that consume this package
(plus the Part 7 replay) as their inputs — they never feed back into the
analysis. Part 8 adds exactly one table — `decisions` (migration `0004`)
— to persist the audit trail and the human-approval status; everything
else is computed.

## Part 7 — Simulation Lab Engine

`backend/app/simulation/` answers one question about an already-analyzed
transaction:

> **What could have been done differently?**

It is a deterministic, read-only counterfactual replay. The recorded
Part 5/6 state (outcome, confidence, consistency status, compound-failure
detection, severity, impact score + scope, root causes, event and evidence
ids) is established as the **baseline (ACTUAL)**. One intervention from a
fixed registry is applied to a *doctored in-memory journey view* — never to
the records — and the existing Part 5 outcome rules are re-run over that
view to derive the simulated classification. Every result carries
`status = SIMULATED` and is a scenario estimate, never an actual outcome, a
prediction or a guarantee.

### Intervention registry (deterministic)

| Intervention | Applicability | Deterministic result |
|---|---|---|
| `DO_NOTHING` | always | control — replays the baseline unchanged (outcome, chain and score preserved) |
| `RETRY_FULFILLMENT` | fulfillment failed / blocked | recovery simulated only when deterministic prerequisites hold (the blocking condition is removable) |
| `ALTERNATIVE_INVENTORY` | inventory allocation failed | allocation succeeds only when an alternative available inventory record exists for the required product/order — otherwise `NOT_EFFECTIVE` (stock is never invented) |
| `SUBSTITUTE_PRODUCT` | substitute relationship exists in the dataset | `NOT_SUPPORTED` when no legitimate substitute relationship is recorded — substitutions are never fabricated |
| `REFUND` | captured payment | financial / customer containment — changes the consequence chain, never claims to fix fulfillment |
| `HUMAN_REVIEW` | always available | escalation simulation — never guarantees recovery |

An intervention that cannot act reports `NOT_APPLICABLE` / `NOT_EFFECTIVE` /
`NOT_SUPPORTED` with an explicit reason — the lab never silently simulates
an impossible action.

### Replay semantics

- **Simulated outcome reuses the Part 5 hierarchy** — the lab does not
  contain a second outcome engine. A remedy never fabricates delivery:
  when the records contain no delivery, the simulated outcome honestly
  stays UNVERIFIABLE (or AT_RISK), never FULFILLED.
- `resolved_failures` / `remaining_failures` / `new_risks` each reference
the rule that produced them, so every simulated change is traceable to
rule ids, event ids and evidence ids.
- **Assumptions are exposed**, e.g. "Simulation assumes alternative
inventory is available", "Simulation assumes fulfillment retry succeeds",
"Simulation does not model real-world customer behavior", "Simulation does
not guarantee delivery".
- **Impact comparison**: `delta = simulated − baseline` impact score —
negative is a simulated improvement, positive a simulated deterioration,
zero no simulated change. It is labelled a *simulated impact delta*, never
"money saved".
- **Comparison ranking** (GET .../compare): simulated impact reduction
first, then fewer remaining failures, then fewer assumptions — a
comparison only, never a recommendation.
- **Deterministic ids**: `simulation_id` is uuid5 over the transaction +
intervention; identical database state + identical intervention →
byte-identical JSON across runs and processes.

Simulation results are deterministic scenario estimates, not predictions or
guarantees.

## Part 8 — AI Decision Agent

`backend/app/decision/` answers one question about an already-analyzed
transaction:

> **Given the verified evidence, business outcome, failure chain, impact
> and simulation results, what should the merchant do next?**

It is the final decision-intelligence layer: REASON → RECOMMEND → WAIT FOR
HUMAN. It never executes anything, never changes the outcome / failure /
impact classifications (Parts 5–7 remain the sole authorities) and never
invents facts.

### Verified-context architecture (the only LLM input)

The service loads the same Parts 3–7 pipeline the analysis package uses
plus the Part 7 simulation report, and `build_context()` reduces it to a
`DecisionContext` — a structured, JSON-serializable bundle of verified
facts:

- Part 5: outcome + outcome confidence + primary reason
- Part 4: consistency status, evidence claims (id, category, claim,
  strength, confidence), evidence gaps, contradictions
- Part 6: compound-failure detection/severity, failure chain
  (kind/stage/label), root-cause kinds, impact score / scope /
  affected-transaction count
- Part 7: every simulation result (status, simulated outcome, impact
  delta, resolved/remaining failure kinds) + comparison ranks
- deterministic flags: payment captured, refund recorded, customer
  impact, mean supporting-evidence confidence, full verified event id set

The LLM receives ONLY this context (rendered deterministically) — never
raw database dumps, free text or event payloads — so it has no path to
invent evidence, customers, amounts or events.

### Closed action registry

The agent may ONLY recommend one of four actions (validated by Pydantic
and by `validate_proposal()`):

| Action | Meaning |
|---|---|
| `DO_NOTHING` | no action is deterministically justified (fulfilled; failed with no capture; refund already recorded) |
| `RECOVER_ROOT_CAUSE` | the root cause is recoverable AND a Part 7 recovery simulation deterministically resolved it |
| `REFUND_OR_CONTAIN` | customer-impacting failure on a captured, unrefunded payment with an applicable refund simulation — containment, never a delivery fix |
| `HUMAN_REVIEW` | evidence insufficient, contradictory, at-risk, or FAILED without a record-justified remedy |

### Deterministic fallback (mandatory — works with no API key)

With `DECISION_LLM_PROVIDER=none` (the default) the agent runs the
fallback registry (`app/decision/rules.py`), first applicable rule wins:

| Priority | Rule | Recommendation |
|---|---|---|
| 10 | `DEC_FULFILLED_DO_NOTHING` | FULFILLED → DO_NOTHING |
| 20 | `DEC_UNVERIFIABLE_HUMAN_REVIEW` | UNVERIFIABLE → HUMAN_REVIEW |
| 30 | `DEC_AT_RISK_HUMAN_REVIEW` | AT_RISK → HUMAN_REVIEW |
| 40 | `DEC_NO_CAPTURE_DO_NOTHING` | FAILED + no capture → DO_NOTHING |
| 50 | `DEC_REFUND_COMPLETE_DO_NOTHING` | FAILED + refund recorded → DO_NOTHING |
| 60 | `DEC_RECOVERABLE_RECOVER` | FAILED + recoverable root cause + recovery simulation actually resolved a failure → RECOVER_ROOT_CAUSE |
| 70 | `DEC_CUSTOMER_IMPACT_CONTAIN` | FAILED + captured + unrefunded + customer impact + refund simulation SIMULATED → REFUND_OR_CONTAIN |
| 80 | `DEC_FAILED_HUMAN_REVIEW` | FAILED without a justified remedy → HUMAN_REVIEW |

Seed-42 decisions: normal/duplicate/delayed webhook → DO_NOTHING;
payment_failed → DO_NOTHING (no capture); inventory_failure →
HUMAN_REVIEW (no recorded stock remedy, no customer signal);
delivery_failure and compound_failure → REFUND_OR_CONTAIN (customer
impact, refund simulation applicable); refund_flow → DO_NOTHING
(containment complete); missing_event and contradictory_event →
HUMAN_REVIEW.

### Confidence (deterministic — never from the LLM)

```
decision_confidence = clamp(0.65 × outcome_confidence
                            + 0.35 × evidence_confidence
                            − 0.05  if consistency INCONSISTENT,
                            0.10 … 0.99)
evidence_confidence  = mean confidence of the supporting evidence items
```

An LLM `llm_confidence` value (if any) is stored as `llm_confidence_signal`
in metadata — an explanation signal only, never used as the system
confidence.

### LLM provider abstraction + code-side validation

- `DecisionLLMProvider` is the abstract contract; `HttpDecisionLLMProvider`
  is a stdlib-only OpenAI-compatible chat-completions implementation
  enabled via `DECISION_LLM_PROVIDER=openai_compatible` (+ base URL, API
  key, model, timeout — see `backend/.env.example`; keys are never
  committed). `build_provider()` returns None when unconfigured.
- `validate_proposal()` rejects: unregistered actions, hallucinated
  evidence ids / event ids (must exist in the verified context),
  unsupported simulation references, empty/over-long reasons, malformed
  JSON and out-of-bounds confidence. Any rejection — or any provider
  error — falls back deterministically and the reason is recorded in
  `metadata.provider_note`.

### Audit trail + human approval

Every decision is persisted idempotently to the `decisions` table
(migration `0004`): `decision_id` (uuid5 over the transaction id), source
(`LLM` or `DETERMINISTIC_FALLBACK`), action, reason, deterministic
confidence, evidence/event ids, the simulation used, alternatives,
`human_approval_required`, and the lifecycle `PENDING → APPROVED /
REJECTED` (with optional rejection reason + timestamps). Repeated GETs
upsert the same row and never reset the approval status. Approving or
rejecting only records the merchant's decision — Part 8 deliberately
stops before any execution layer. Only the concise rationale is stored;
hidden chain-of-thought is never persisted or exposed.

### API

- `GET /api/v1/decisions/{transaction_id}` — generate (idempotently
  persist) the decision; 404 unknown transaction.
- `POST /api/v1/decisions/{decision_id}/approve` — PENDING → APPROVED
  (optional audit note); 404 unknown decision, 409 invalid transition.
- `POST /api/v1/decisions/{decision_id}/reject` — PENDING → REJECTED
  (optional reason); 404 unknown decision, 409 invalid transition.

### Frontend

The transaction detail page renders an **AI DECISION** section after
SIMULATION LAB: source label (AI vs DETERMINISTIC FALLBACK), recommended
action with hint, concise reason, deterministic decision/evidence
confidence, evidence chips, simulation basis, alternatives, the approval
status and APPROVE / REJECT controls (with an optional rejection-reason
input). Everything is labelled "recommendation only — never executes".

## Part 9 — Razorpay TEST-MODE webhook ingestion

`backend/app/ingestion/razorpay.py` + `backend/app/ingestion/adapters/
razorpay.py` add the first real provider adapter to the Part 3 pipeline:

```
Razorpay webhook (TEST MODE)
   → POST /api/v1/webhooks/razorpay
   → verify (HMAC-SHA256 X-Razorpay-Signature, or explicit demo mode)
   → parse + extract deterministic identities (event id, payment id)
   → record the raw delivery (Webhook row, signature_verified flag)
   → RazorpayWebhookAdapter → canonical events
   → existing Part 3 pipeline (validate → normalize → correlate →
     idempotency → persist)
   → Journey → Evidence → Consistency → Outcome → Failure/Impact →
     Simulation → AI Decision → Human Approval (unchanged)
```

### Signature verification (environment-configured)

| State | Behavior |
|---|---|
| `RAZORPAY_WEBHOOK_SECRET` set + valid signature | accept; `signature_verified=true`, mode `razorpay_test_mode` |
| secret set + invalid signature | reject 400 (`Invalid X-Razorpay-Signature`) |
| secret set + missing signature | reject 400 (`Missing X-Razorpay-Signature`) |
| no secret + `X-PAYSCAPE-DEMO: 1` + `DEMO_MODE=true` | accept as explicit demo delivery; `signature_verified=false`, mode `demo` — never presented as verified |
| no secret + no demo header | reject 400 (cannot verify) |

The secret is configured through `RAZORPAY_WEBHOOK_SECRET` only — never
hardcoded, never logged. The signature is HMAC-SHA256 of the RAW request
body, compared in constant time (`hmac.compare_digest`).

### Supported webhook events (mapped onto the existing registry)

| Razorpay event | Canonical events (after normalization) |
|---|---|
| `payment.created` | `PAYMENT_CREATED` (PAYMENT_PROVIDER) + `WEBHOOK_RECEIVED` (WEBHOOK) |
| `payment.authorized` | `PAYMENT_AUTHORIZED` + `WEBHOOK_RECEIVED` |
| `payment.captured` | `PAYMENT_CAPTURED` + `WEBHOOK_RECEIVED` |
| `payment.failed` | `PAYMENT_FAILED` + `WEBHOOK_RECEIVED` |
| `refund.created` | `REFUND_INITIATED` + `WEBHOOK_RECEIVED` |
| `refund.processed` | `REFUND_COMPLETED` + `WEBHOOK_RECEIVED` |
| `refund.failed` | `REFUND_FAILED` + `WEBHOOK_RECEIVED` |
| anything else | preserved as UNKNOWN — never dropped, never guessed |

Event-type spelling is kept raw; the centralized Part 2 registry
(`app/core/events.py`) and Part 3 normalizer do the mapping (two Razorpay
spellings were added: `refund.created` → `REFUND_INITIATED` and
`refund.processed` → `REFUND_COMPLETED`). There is still exactly one event
registry and one canonical event model — no second event system.

### Idempotency and correlation

- **Idempotency** reuses the Part 3 mechanism: the same provider event id
delivered twice produces `DUPLICATE` ingestion results and a
`DUPLICATE`-status webhook row — zero duplicate canonical events.
- **Correlation** uses the explicit Razorpay payment id
(`payload.payment.entity.id` / `payload.refund.entity.payment_id`) through
correlation priority 4 (provider identifiers) — never fuzzy matching.
- A webhook whose payment cannot be linked is **preserved as an ORPHAN**
in the response (nothing persisted) — the raw event is never invented
into a transaction.

### Safety boundary

The endpoint only records the delivery (Webhook row) and canonical events.
It performs NO refunds, payments, messages or external calls — real
financial execution remains out of scope, and the system still stops at
AI RECOMMENDATION → HUMAN APPROVAL (records only).

### Frontend

The transaction detail page opens with a **pipeline narrative strip** —
`PAYMENT → JOURNEY → EVIDENCE → CONSISTENCY → OUTCOME → FAILURE → IMPACT
→ SIMULATION → AI DECISION → HUMAN APPROVAL` — with per-stage status dots
and live detail (payment status, outcome, recommended action, approval
status), so the hackathon story is visually obvious without redesigning
the page.

## Future architecture (planned)

A transaction does not end at payment success. The full pipeline:

```
Customer Intent
      │
      ▼
Event Ingestion          ✅ Part 3 + Part 9 (deterministic,
                             provider-agnostic + Razorpay TEST-MODE
                             webhook adapter, HMAC-verified)
      │
      ▼
Journey Reconstruction   ✅ Part 3 (chronological + graph + integrity)
      │
      ▼
Evidence Engine          ✅ Part 4 (what do the records support?)
      │
      ▼
Consistency Engine       ✅ Part 4 (do the observed records agree?)
      │
      ▼
Outcome Engine           ✅ Part 5 (FULFILLED · AT_RISK · FAILED · UNVERIFIABLE)
      │
      ▼
Compound Failure Engine  ✅ Part 6 (failure chains + root cause)
      │
      ▼
Consequence / Impact     ✅ Part 6 (OBSERVED · DERIVED · POTENTIAL, scope)
      │
      ▼
Simulation Lab           ✅ Part 7 (deterministic, read-only replay)
      │
      ▼
AI Decision Agent        ✅ Part 8 (verified context, closed registry,
                             LLM or deterministic fallback)
      │
      ▼
Human Approval           ✅ Part 8 (PENDING → APPROVED / REJECTED —
                             records only, never executes)
      │
      ▼
Action execution         later part (real provider actions behind
                             explicit operator confirmation)
```

**Parts 3–9 reconstruct, verify, classify, explain, simulate and ingest —
with code, not AI.** The engines under `backend/app/{journey,evidence,
consistency,outcome,failures,impact,simulation}` are live and
deterministic; Part 8 adds the Decision Agent
(`backend/app/decision/`) whose LLM path is optional (deterministic
fallback by default) and never executes anything; Part 9 adds the
Razorpay TEST-MODE webhook adapter without changing the pipeline. Only
`backend/app/{agents,rules}` remain documented placeholders, and the
Part 1 graph primitives in `backend/app/graph/base.py` are superseded by
the deterministic `app/journey/graph.py`.

See also:

- `docs/ai-design.md` — how agents will reason over events.
- `docs/methodology.md` — outcome definitions and classification method.
- `docs/limitations.md` — what Parts 3–9 deliberately do not do.
