# PAYSCAPE-X

**From payment success to business outcome.**

> A successful payment does not necessarily mean a successful business transaction.

PAYSCAPE-X analyses the complete journey — **Customer Intent → Payment →
Order → Inventory → Fulfillment → Delivery → Customer Outcome** — and
determines whether the intended business outcome was `FULFILLED`, `AT_RISK`,
`FAILED` or `UNVERIFIABLE`.

## 1. What PAYSCAPE-X is

A full-stack payment-outcome intelligence platform: a serious, control-center
style application that tells operators not just *"did the money move?"* but
*"did the customer actually get what they paid for?"*

## 2. Core problem

Payment dashboards celebrate a 98% success rate while customers quietly fail
to receive their orders. The gap between **Payment Success** and **Business
Outcome Success** is invisible to most tools. PAYSCAPE-X surfaces that gap by
reconstructing each transaction's full journey from structured events and
classifying the real business outcome.

## 3. Current scope — Part 9 (Razorpay TEST-MODE ingestion + demo polish)

Part 1 shipped the clean application foundation (control-center UI, FastAPI
with health endpoints, portable PostgreSQL schema, typed API client, Demo
Mode, future-module placeholders).

Part 2 built the **real data and event foundation**: a full PostgreSQL
schema for the business journey, a deterministic synthetic data generator
(150 coherent journeys, 10 scenario types, 2,170 unified events), a
structural data-integrity validator, read-only APIs for transactions /
events / scenarios, and real-data frontend pages.

Part 3 added the **deterministic event-ingestion and journey-reconstruction
layer**: a reusable ingestion pipeline (adapters → validation →
normalization → correlation → idempotent persistence), canonical
chronological journey reconstruction, a deterministic journey graph
(PRECEDES / TRIGGERS / BELONGS_TO / CORRELATES_WITH / DERIVED_FROM), and a
structural integrity report (duplicates, missing-event candidates,
contradictions, delayed, out-of-order, unknown and orphan events).

Part 4 added the **evidence and consistency engines**: a deterministic
Evidence Engine (21 claim rules, 11 categories, DIRECT / CORROBORATED /
INDIRECT / MISSING / CONTRADICTED strengths, gaps and preserved
contradictions) and a Consistency Engine (16 documented invariants
evaluated as PASS / VIOLATION / INSUFFICIENT_EVIDENCE / NOT_APPLICABLE — a
missing event is never a violation).

Part 5 adds the **Business Outcome Engine** on top — the answer to the
product's core question, *"did the business transaction actually
succeed?"*:

- **Outcome Engine** (`backend/app/outcome/`): classifies every
  reconstructed transaction into exactly one of **FULFILLED / AT_RISK /
  FAILED / UNVERIFIABLE** using an explicit, documented decision hierarchy
  of 11 deterministic rules (contradiction → payment failure → delivery
  failure → business failure markers → allocation failure → cancellation →
  delivered → at-risk states → insufficient evidence).
  **FULFILLED requires a delivery-completed record** — a successful payment
  is never FULFILLED on its own, and business failure (out of stock, never
  confirmed, delivery failed, cancelled) is distinguished from payment
  failure.
- **Deterministic confidence**: a base score per outcome minus fully
  traced, documented adjustments (delayed webhook, out-of-order events,
  consistency violations, contradicted evidence). Not an LLM probability,
  not fake certainty — confidence reflects record strength.
- **Auditable output**: every outcome carries a primary reason plus
  corroborating reasons, each with `rule_id`, `code`, `message`, severity
  and full **traceability back to the exact evidence ids and event ids**
  that support it; the 11-rule evaluation trace and every confidence
  adjustment are returned for inspection.
- **API**: `GET /api/v1/outcome/{id}`; `GET /api/v1/analysis/{id}` now
  returns journey + evidence + consistency + **outcome** (existing Part 4
  fields unchanged).
- **Frontend**: the transaction detail page now renders an **OUTCOME**
  section after JOURNEY / EVIDENCE / CONSISTENCY with a visually distinct
  badge per state, confidence, primary/corroborating reasons, supporting
  and blocking evidence, consistency status and evidence completeness.

Part 6 adds the **Compound Failure Engine and the Consequence / Impact
Engine** on top of the Part 5 outcome:

- **Compound Failure Engine** (`backend/app/failures/`): for every FAILED
  transaction it identifies whether several related problems form a
  connected failure chain rather than an isolated incident. It builds a
  **failure chain** (nodes ordered along the promise stages payment →
  webhook → order → inventory → fulfillment → shipment → delivery →
  customer, edges such as `BLOCKS` / `LEADS_TO` / `IMPACTS` with
  rule ids), selects a **root cause** through an explicit priority table
  (the earliest event — e.g. a webhook delay — is never assumed to be the
  root), and reports deterministic severity (LOW / MEDIUM / HIGH /
  CRITICAL), classification (OBSERVED / DERIVED) and confidence. A
  compound failure is only reported when the outcome is FAILED and at
  least two chain nodes span at least two distinct stages; a lone payment
  failure is a single-stage failure, never a compound one, and
  UNVERIFIABLE / FULFILLED transactions never produce a chain.
- **Consequence / Impact Engine** (`backend/app/impact/`): determines the
  downstream consequences of the detected failure and strictly separates
  **OBSERVED** (stated by a record), **DERIVED** (follows deterministically
  from records) and **POTENTIAL** (a possible future state signalled by a
  customer complaint/contact — explicitly NOT a prediction). Categories:
  PAYMENT, ORDER, INVENTORY, FULFILLMENT, SHIPMENT, DELIVERY, CUSTOMER,
  REFUND, REVENUE, OPERATIONAL. It also computes **cross-transaction
  impact**: when the same `INVENTORY_OUT_OF_STOCK` SKU hit other orders,
  the scope is MULTI_TRANSACTION and every affected transaction (with its
  own Part 5 outcome) is listed — relationships are only ever built from
  explicit shared identifiers (the SKU), never from fuzzy matching. A
  transparent **impact score** (0–100, formula in the docs and returned
  component-by-component in the payload) summarises severity,
  consequences and cohort size; it is not a financial-loss estimate and
  not a prediction.
- **API**: `GET /api/v1/failures/{id}`, `GET /api/v1/impact/{id}` and the
  dataset list `GET /api/v1/failures` (severity / failure_type / outcome /
  scope filters + pagination); `GET /api/v1/analysis/{id}` now returns
  journey + evidence + consistency + outcome + **compound_failure** +
  **impact** (existing Part 4/5 fields unchanged).
- **Frontend**: the transaction detail page now renders **COMPOUND
  FAILURE** (detected/not-detected, severity, failure chain,
  root cause) and **CONSEQUENCES / IMPACT** (observed / derived /
  potential consequence groups with distinct visual styles, single vs
  multi-transaction scope, shared-SKU banner, affected-transaction list,
  impact score) sections after OUTCOME. The **/failures page** now shows
  the real detected compound failures from the engine instead of demo
  placeholders.

Part 7 adds the **Simulation Lab** — a deterministic, read-only
intervention-comparison layer on top of the Part 6 analysis:

- **Simulation Engine** (`backend/app/simulation/`): answers *"what could
  have been done differently?"* for an already-analyzed transaction. It
  establishes the recorded Part 5/6 state as the **baseline**, applies one
  intervention from a fixed registry — `DO_NOTHING` (control), `RETRY_
  FULFILLMENT`, `ALTERNATIVE_INVENTORY`, `SUBSTITUTE_PRODUCT`, `REFUND`,
  `HUMAN_REVIEW` — to a doctored in-memory journey view, and re-runs the
  existing Part 5 outcome rules over that view to derive a **SIMULATED**
  outcome. An intervention that cannot act reports `NOT_APPLICABLE` /
  `NOT_EFFECTIVE` / `NOT_SUPPORTED`: stock is never invented, substitute
  products are never fabricated, and a remedy never fabricates a delivery
  (unresolved journeys honestly stay UNVERIFIABLE).
- **Deterministic comparison**: each simulation reports resolved /
  remaining failures, new risks, explicit assumptions and rule
  references; the impact delta (`simulated − baseline` impact score,
  negative = simulated improvement) is a *simulated impact delta*, never
  money saved. The lab is strictly read-only and the ranked comparison is
  not a recommendation.
- **API**: `GET /api/v1/simulations/{id}`, `POST
  /api/v1/simulations/{id}/run`, `GET /api/v1/simulations/{id}/compare`.
- **Frontend**: the transaction detail page gains a **SIMULATION LAB**
  section after CONSEQUENCES / IMPACT, and the standalone **/simulation
  page** shows the baseline, per-intervention cards and the comparison
  table with the best simulated result highlighted (never "recommended").

Part 8 adds the **AI Decision Agent + Human Approval** — the final
decision-intelligence layer that answers *"given the verified evidence,
business outcome, failure chain, impact and simulation results, what
should the merchant do next?"*:

- **Decision Agent** (`backend/app/decision/`): reasons ONLY over a
  structured verified context built from Parts 3–7 (outcome, evidence
  claims, consistency, contradictions, failure chain, root causes,
  impact, simulation results). It recommends exactly one action from a
  closed registry — `DO_NOTHING`, `RECOVER_ROOT_CAUSE`,
  `REFUND_OR_CONTAIN`, `HUMAN_REVIEW` — never an arbitrary string.
- **LLM provider abstraction + deterministic fallback**: the agent works
  with NO API key — `DECISION_LLM_PROVIDER=none` (the default) runs the
  deterministic fallback rule registry (8 documented rules: fulfilled →
  do nothing, unverifiable/at-risk → human review, failed without
  capture or with a completed refund → do nothing, recoverable root
  cause that a Part 7 simulation actually resolves → recover,
  customer-impacting failure with an applicable refund simulation →
  contain, otherwise → human review). An OpenAI-compatible HTTP provider
  can be enabled via environment variables; its output is validated
  against the verified context — unsupported actions, hallucinated
  evidence/event ids, unsupported simulation references and malformed
  JSON are rejected and the deterministic fallback is used. An LLM
  confidence value is an explanation signal only; `decision_confidence`
  is always computed deterministically from verified inputs.
- **Human approval workflow**: every decision is persisted as an
  auditable row (`PENDING → APPROVED / REJECTED` with an optional
  rejection reason, deterministic `decision_id`, full references to
  evidence/event/simulation ids, decision source `LLM` or
  `DETERMINISTIC_FALLBACK`). Approval ONLY records the merchant's
  decision — Part 8 never executes refunds, payments, messages or any
  external action (`REASON → RECOMMEND → WAIT FOR HUMAN`).
- **API**: `GET /api/v1/decisions/{id}`, `POST
  /api/v1/decisions/{decision_id}/approve`, `POST
  /api/v1/decisions/{decision_id}/reject` (404 unknown, 409 invalid
  approval transition).
- **Frontend**: the transaction detail page gains an **AI DECISION**
  section after SIMULATION LAB showing the recommended action, why,
  deterministic confidence, evidence chips, simulation basis,
  alternatives, the LLM-vs-fallback source label and the APPROVE /
  REJECT workflow — clearly labelled "recommendation only, never
executes".

Part 9 adds the **Razorpay TEST-MODE webhook integration + hackathon
polish** — the final implementation part:

- **Razorpay webhook adapter** (`backend/app/ingestion/adapters/
  razorpay.py` + `backend/app/ingestion/razorpay.py`): accepts Razorpay
  TEST-MODE webhook events and runs them through the SAME Part 3 pipeline
  as the synthetic dataset (adapter → validate → normalize → correlate →
  idempotency → persist). Supported events: `payment.created` /
  `payment.authorized` / `payment.captured` / `payment.failed` and
  `refund.created` / `refund.processed` / `refund.failed` — each mapped
  onto the centralized event registry (e.g. `payment.captured` →
  `PAYMENT_CAPTURED` + `WEBHOOK_RECEIVED`, `refund.processed` →
  `REFUND_COMPLETED`). Unknown event types are preserved and marked
  UNKNOWN, never dropped.
- **Signature verification**: when `RAZORPAY_WEBHOOK_SECRET` is set, the
  raw body's HMAC-SHA256 signature is verified against the
  `X-Razorpay-Signature` header — valid signatures are accepted, invalid
  and missing signatures are rejected with 400. With no secret
  configured, the endpoint only accepts explicit demo-mode deliveries
  (`X-PAYSCAPE-DEMO: 1`, requires `DEMO_MODE=true`) and records
  `signature_verified=false` — an unverified delivery is never presented
  as verified. Secrets are never hardcoded or logged.
- **Idempotency + correlation**: a redelivered event (same provider
  event id) creates zero duplicate canonical events — the second delivery
  records a DUPLICATE webhook row. Payment linking uses the explicit
  Razorpay payment id only; a webhook for an unknown payment is preserved
  as an ORPHAN in the response and nothing is persisted.
- **Safety boundary**: the endpoint only records the delivery (Webhook
  row) and canonical events. It performs NO refunds, payments, messages
  or external calls — the pipeline still stops at AI RECOMMENDATION →
  HUMAN APPROVAL.
- **Frontend polish**: the transaction detail page now opens with a
  pipeline narrative strip — `PAYMENT → JOURNEY → EVIDENCE →
  CONSISTENCY → OUTCOME → FAILURE → IMPACT → SIMULATION → AI DECISION →
  HUMAN APPROVAL` — so the demo story is visually obvious at a glance.

**AI reasons. CODE VERIFIES.** Parts 3–9 contain zero LLM calls, zero
embeddings, zero AI-generated conclusions, zero recommendations and zero
autonomous actions in the deterministic pipeline (the only LLM anywhere is
the Part 8 Decision Agent's optional, validated, non-executing provider).
The pipeline
`RAW EVENTS → JOURNEY RECONSTRUCTION → EVIDENCE ENGINE → CONSISTENCY ENGINE
→ OUTCOME ENGINE → COMPOUND FAILURE + IMPACT` is fully deterministic — the
same input produces byte-equivalent JSON (outcome, confidence, reasons,
failure chain, consequences and references all included). Part 7 adds the
intentional exception to "no simulations": the Simulation Lab is
deterministic and read-only and every result is labelled SIMULATED — a
scenario estimate, never a prediction, a guarantee or a recommendation.
Part 8 adds the intentional exception to "no AI": the Decision Agent may
use an LLM, but it reasons ONLY over verified facts, may ONLY pick a
registered action, is validated by code (invalid output falls back
deterministically), and NEVER executes anything — human approval only
records the merchant's decision. Part 9 adds the intentional exception to
"no provider integration": Razorpay TEST-MODE webhooks are accepted,
verified and ingested, but the system never performs a real financial
transaction and clearly labels DEMO / SYNTHETIC data vs verified
TEST-MODE deliveries. Part 6 reconstructs evidence about a failure; it
does not predict what happens next — POTENTIAL consequences are signalled
possibilities, never facts.

## 4. Architecture overview

```
Frontend (Next.js)
   ↑  HTTP/JSON via typed client
API (FastAPI)  /health · /api/v1/health · /api/v1/transactions
               /api/v1/events · /api/v1/scenarios · /api/v1/journeys/**
               /api/v1/evidence · /api/v1/consistency · /api/v1/analysis
               /api/v1/outcome · /api/v1/failures · /api/v1/impact
               /api/v1/simulations/** · /api/v1/decisions/**
               /api/v1/webhooks/razorpay (POST, TEST MODE)
   ↓
Services (modular, no logic in components)
   ↓
Ingestion pipeline (adapters → validate → normalize → correlate → persist)
        ↑
Razorpay TEST-MODE webhooks (HMAC-verified or explicit demo-mode; adapter
   → existing Part 3 pipeline; idempotent; no financial actions)
   ↓
Journey reconstruction (chronological replay + graph + integrity)
   ↓
Evidence Engine  (what do the records support? strengths, gaps, contradictions)
   ↓
Consistency Engine (do the records agree? PASS / VIOLATION / INSUFFICIENT)
   ↓
Outcome Engine (FULFILLED · AT_RISK · FAILED · UNVERIFIABLE)
   ↓
Compound Failure Engine (failure chains + root cause)
   ↓
Consequence / Impact Engine (observed · derived · potential, scope, score)
   ↓
Simulation Lab (deterministic, read-only intervention replay → SIMULATED)
   ↓
AI Decision Agent (verified-context LLM or deterministic fallback)
   ↓
Human Approval (PENDING → APPROVED / REJECTED — records only)
   ↓
Database (PostgreSQL — SQLAlchemy + Alembic)
   ↑
Synthetic Event Pipeline (deterministic generator → TransactionEvent)
```

The data model represents one **business transaction journey** per
correlation id: Merchant → Customer → Order → Payment → Webhook →
TransactionEvent → Inventory → Fulfillment → Shipment → Delivery →
Customer Message. Every event carries a `correlation_id` so future modules
can reconstruct the complete chronological journey.

The pipeline through Human Approval is live:
`RAW EVENTS → JOURNEY RECONSTRUCTION → EVIDENCE ENGINE → CONSISTENCY ENGINE
→ OUTCOME ENGINE → COMPOUND FAILURE + IMPACT → SIMULATION LAB (read-only)
→ AI DECISION → HUMAN APPROVAL → (recorded decision only)`. The Simulation
Lab replays the recorded journey against deterministic interventions; it
never modifies the transaction and it is not a recommendation engine. The
Decision Agent recommends one registered action over verified facts and
waits for human approval; approving never executes the action. Razorpay
TEST-MODE webhook events enter at the ingestion layer and flow through the
exact same pipeline — the payload is verified, correlated by explicit
payment id, deduplicated, and recorded; no financial action is ever
performed. Every future module consumes structured events. See
`docs/architecture.md`.

## 5. Technology stack

| Layer     | Technology |
|-----------|------------|
| Frontend  | Next.js 16, React 19, TypeScript, Tailwind CSS, shadcn/ui (Base UI), lucide-react |
| Backend   | Python 3, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, psycopg 3 |
| Database  | PostgreSQL (SQLite for local tests) |
| Tests     | pytest (backend), Vitest + Testing Library (frontend) |

## 6. Repository structure

```
payscape-x/
├── frontend/
│   ├── app/            # routes: dashboard, transactions/[id], investigation/[id],
│   │                   #   failures, simulation, actions, events, settings
│   ├── components/     # layout, dashboard, shared, ui (shadcn)
│   ├── lib/            # api-client, demo-mode, demo-data (seed layer), utils
│   ├── hooks/          # use-backend-health
│   ├── types/          # shared domain types (Merchant, Order, Payment, …)
│   ├── tests/          # vitest: rendering + API client
│   └── public/
├── backend/
│   ├── app/
│   │   ├── api/        # versioned HTTP routes (v1): health, transactions,
│   │   │               #   events, scenarios, journeys, evidence,
│   │   │               #   consistency, analysis, outcome, failures, impact,
│   │   │               #   simulation, decisions, webhooks
│   │   ├── ingestion/  # Part 3: adapters, validator, normalizer, service;
│   │   │               #   Part 9: razorpay.py (signature + parsing) and
│   │   │               #   adapters/razorpay.py (TEST-MODE webhook adapter)
│   │   ├── journey/    # Part 3: reconstructor, correlation, integrity, graph
│   │   ├── evidence/   # Part 4: collector, strength, models
│   │   ├── consistency/# Part 4: rules, evaluator, models
│   │   ├── outcome/    # Part 5: rules, engine, models (outcome engine)
│   │   ├── failures/   # Part 6: compound failure engine (chain, root cause)
│   │   ├── impact/     # Part 6: consequences + cross-transaction impact
│   │   ├── simulation/ # Part 7: deterministic read-only Simulation Lab
│   │   ├── decision/   # Part 8: AI Decision Agent (context, LLM provider,
│   │   │               #   validation, deterministic fallback rules)
│   │   ├── models/     # SQLAlchemy entities (17 tables, journey model)
│   │   ├── schemas/    # Pydantic contracts (incl. webhook response)
│   │   ├── services/   # health, transactions, events, scenarios, journeys,
│   │   │               #   evidence, consistency, analysis, outcome,
│   │   │               #   failures, impact, simulation, decisions,
│   │   │               #   razorpay_webhook, domain_context, validation
│   │   ├── synthetic/  # deterministic dataset generator (data + scenarios)
│   │   ├── core/       # config, database, logging, exceptions, enums, events
│   │   └── agents/ rules/            # future-module placeholders (interfaces
│   │                   #   only — agents & rules; graph/ is superseded and
│   │                   #   simulation/ is the live Part 7 Simulation Lab)
│   ├── alembic/        # migrations (0001 foundation, 0002 journey schema,
│   │                   #   0003 ingestion_sequence, 0004 decisions —
│   │                   #   Parts 4–9 add no tables; Part 8 adds the
│   │                   #   decision/approval table)
│   ├── tests/          # pytest: health, config, database, generator,
│   │                   #   scenarios, validation, read APIs, ingestion,
│   │                   #   journey reconstruction, journey APIs, evidence,
│   │                   #   consistency, analysis, outcome APIs, compound
│   │                   #   failure, impact, failures dataset, simulation,
│   │                   #   decision agent + decision APIs
│   ├── requirements.txt
│   └── .env.example
├── data/               # scenarios/ + samples/ (synthetic fixtures, later parts)
├── docs/               # architecture.md, ai-design.md, methodology.md, limitations.md
├── .env.example
└── README.md
```

## 7. Environment variables

Never commit secrets. All configuration is environment-driven; copy the
templates and fill real values locally.

| Where      | File to copy          | Key variables |
|------------|-----------------------|---------------|
| Backend    | `backend/.env.example` → `backend/.env` | `DATABASE_URL`, `CORS_ORIGINS`, `APP_ENV`, `LOG_LEVEL`, `DEMO_MODE`, `RAZORPAY_WEBHOOK_SECRET` |
| Frontend   | `frontend/.env.example` → `frontend/.env.local` | `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_DEMO_MODE`, `NEXT_PUBLIC_APP_ENV` |

`.env*` files are git-ignored; `.env.example` templates are committed.

## 8. Local setup

Prerequisites: Node.js ≥ 20, Python ≥ 3.11, PostgreSQL (optional for the
frontend/health checks — required for migrations against a real DB).

```bash
# Backend dependencies
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   |  macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env

# Frontend dependencies
cd ../frontend
npm install
cp .env.example .env.local
```

## 9. Database setup

**PostgreSQL is the primary database.** SQLAlchemy + Alembic manage the
schema; tables are only ever created through migrations (never at
application startup). SQLite remains supported for isolated tests.

```bash
cd backend

# 1) Create the database (local PostgreSQL), e.g.:
#    createdb payscape_x
# 2) Point DATABASE_URL at it in backend/.env:
#    DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:5432/payscape_x

# 3) Run migrations
alembic upgrade head
```

The schema (migrations `0001` + `0002` + `0003` + `0004`) creates 17 business tables:
`merchants`, `customers`, `orders`, `payments`, `webhooks`, `products`,
`inventory_records`, `inventory_events`, `fulfillments`,
`fulfillment_events`, `shipments`, `delivery_events`, `customer_messages`,
`refunds`, `scenario_instances`, the unified `transaction_events` stream and
the Part 8 `decisions` table (audit trail + human-approval status).
Enums are stored as VARCHAR + CHECK (portable to PostgreSQL and SQLite),
payloads use JSON with a JSONB variant on PostgreSQL, and every journey is
traceable via `correlation_id`. Migration `0003` adds
`transaction_events.ingestion_sequence` — the authoritative insertion order
the Part 3 reconstruction layer compares against timestamps to detect
out-of-order ingestion (`created_at` alone ties on bulk loads). Migration
`0004` adds `decisions` — one deterministic, idempotent row per
transaction recording the recommendation, its source, references and the
approval lifecycle; Parts 4–9 added no tables.

## 9b. Synthetic dataset (seed / reset / validate)

```bash
cd backend

# Seed the deterministic synthetic dataset (seed 42 by default)
.venv/Scripts/python -m app.seed

# Different deterministic dataset
.venv/Scripts/python -m app.seed --seed 7

# Clear and regenerate (development/demo only — refuses to run unless
# APP_ENV is development/demo/test)
.venv/Scripts/python -m app.seed --reset

# Structural data-integrity validation (no business-state judgement)
.venv/Scripts/python -m app.seed --validate
```

Default dataset: **NovaCart Commerce** · 100 customers · 30 products · 150
orders · 150 payments · 2,170 unified transaction events across 10
scenarios: Normal Success (70), Payment Failed (15), Duplicate Webhook
(10), Delayed Webhook (10), Inventory Failure (10), Delivery Failure (10),
Refund Flow (10), Missing Event (5), Contradictory Event (5), Compound
Failure (5). Running the generator twice with the same seed reproduces the
exact dataset (ids, timestamps, amounts).

## 10. Start the frontend

```bash
cd frontend
npm run dev        # http://localhost:3000
```

Other useful commands:

```bash
npm run build      # production build
npm run typecheck  # tsc --noEmit
npm test           # vitest
```

## 11. Start the backend

```bash
cd backend
.venv/Scripts/python -m uvicorn app.main:app --reload   # Windows
.venv/bin/python -m uvicorn app.main:app --reload       # macOS/Linux
```

Interactive docs: http://localhost:8000/docs

Run the backend test suite:

```bash
.venv/Scripts/python -m pytest     # Windows
.venv/bin/python -m pytest         # macOS/Linux
```

## 12. API endpoints

Health:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/health
```

```json
{
  "status": "ok",
  "service": "payscape-x",
  "version": "0.1.0",
  "database": "ok"
}
```

`database` reports `"unavailable"` when PostgreSQL is not reachable — the
API never fakes connectivity. The frontend calls this endpoint and shows
**Backend Connected** / **Backend Unavailable** accordingly (top bar and
sidebar).

Part 2 read-only resources (all under `/api/v1`):

| Endpoint | Purpose | Filters / pagination |
|---|---|---|
| `GET /transactions` | Payment-level journeys | `limit`, `offset`, `scenario` (slug or type), `payment_status` |
| `GET /transactions/{id}` | Full journey: order, payment, customer, scenario, chronological events | — |
| `GET /events` | Unified chronological event stream | `limit`, `offset`, `event_type`, `source`, `correlation_id` |
| `GET /scenarios` | All 10 synthetic scenario types with transaction/event counts | — |
| `GET /scenarios/{scenario_id}` | Scenario detail: transactions, event count, sample timeline | — |
| `GET /journeys/{id}` | Reconstructed journey: chronological events + graph + integrity | — |
| `GET /journeys/{id}/graph` | Deterministic journey graph (nodes + edges with rule ids/reasons) | — |
| `GET /journeys/{id}/integrity` | Structural integrity report (duplicates, contradictions, missing candidates, delayed, out-of-order, unknown, orphans) | — |
| `GET /evidence/{id}` | Deterministic evidence report: claims with strength/confidence, gaps, contradictions | — |
| `GET /consistency/{id}` | Deterministic rule evaluation: PASS / VIOLATION / INSUFFICIENT_EVIDENCE / NOT_APPLICABLE + overall_integrity | — |
| `GET /outcome/{id}` | Deterministic business outcome: FULFILLED / AT_RISK / FAILED / UNVERIFIABLE + confidence, reasons, rule trace | — |
| `GET /failures/{id}` | Compound failure analysis: detected / not detected, severity, failure chain with edges, root cause(s), OBSERVED / DERIVED classification | — |
| `GET /failures` | Detected compound failures across the dataset | `limit`, `offset`, `severity`, `failure_type`, `outcome`, `scope` |
| `GET /impact/{id}` | Consequence / impact analysis: observed / derived / potential consequences, single vs multi-transaction scope, affected cohort, impact score | — |
| `GET /simulations/{id}` | Simulation Lab: baseline (actual outcome, severity, root cause, impact score/scope) + every intervention's SIMULATED result + ranked comparison | — |
| `POST /simulations/{id}/run` | Run one deterministic intervention (`DO_NOTHING`, `RETRY_FULFILLMENT`, `ALTERNATIVE_INVENTORY`, `SUBSTITUTE_PRODUCT`, `REFUND`, `HUMAN_REVIEW`) — read-only, labelled SIMULATED | body `{ "intervention": "..." }` |
| `GET /simulations/{id}/compare` | Ranked comparison table (impact reduction → fewer remaining failures → fewer assumptions; not a recommendation) | — |
| `GET /decisions/{id}` | AI Decision Agent: recommended action from the closed registry (DO_NOTHING / RECOVER_ROOT_CAUSE / REFUND_OR_CONTAIN / HUMAN_REVIEW), reason, deterministic confidence, evidence/event/simulation references, source (LLM or DETERMINISTIC_FALLBACK), approval status — generated idempotently, never executes | — |
| `POST /decisions/{decision_id}/approve` | Record merchant approval: PENDING → APPROVED (audit-trail note optional) — records only, never executes the action | body `{ "note": "..." }` |
| `POST /decisions/{decision_id}/reject` | Record merchant rejection: PENDING → REJECTED with optional reason (404 unknown decision, 409 invalid transition) | body `{ "reason": "..." }` |
| `POST /webhooks/razorpay` | Razorpay TEST-MODE webhook ingestion: HMAC-verify (or explicit demo mode), record delivery, run through the Part 3 pipeline — idempotent, orphan-preserving, no financial actions | body = raw Razorpay event; header `X-Razorpay-Signature` (or `X-PAYSCAPE-DEMO: 1` in demo mode) |
| `GET /analysis/{id}` | Combined deterministic package: journey + evidence + consistency + outcome + compound failure + impact in one pipeline | — |

Example normal journey (`GET /api/v1/scenarios/normal_success`):

```
ORDER_CREATED → PAYMENT_CREATED → PAYMENT_AUTHORIZED → PAYMENT_CAPTURED
→ WEBHOOK_SENT → WEBHOOK_RECEIVED → ORDER_CONFIRMED → INVENTORY_RESERVED
→ FULFILLMENT_CREATED → FULFILLMENT_PROCESSING → FULFILLMENT_PACKED
→ FULFILLMENT_SHIPPED → SHIPMENT_CREATED → SHIPMENT_IN_TRANSIT
→ DELIVERY_OUT_FOR_DELIVERY → DELIVERY_COMPLETED
```

Example compound failure (`GET /api/v1/scenarios/compound_failure`):

```
PAYMENT_CAPTURED → INVENTORY_RESERVED → WEBHOOK_RECEIVED
→ WEBHOOK_DELAYED → ORDER_NOT_CONFIRMED → INVENTORY_RESERVATION_EXPIRED
→ INVENTORY_OUT_OF_STOCK → NO_FULFILLMENT → CUSTOMER_COMPLAINT
```

Example business outcome (`GET /api/v1/outcome/{id}` on that journey):

```json
{
  "outcome": "FAILED",
  "confidence": 0.9,
  "primary_reason": { "code": "ORDER_NOT_CONFIRMED", "rule_id": "BUSINESS_FAILURE_MARKERS", "message": "Confirmation SLA expired …" },
  "reasons": [ { "code": "ORDER_NOT_CONFIRMED", … }, { "code": "INVENTORY_ALLOCATION_FAILED", … } ]
}
```

The payment was captured — the classification is a business failure, not a
payment failure.

Example compound failure (`GET /api/v1/failures/{id}` on that journey):

```json
{
  "detected": true,
  "severity": "CRITICAL",
  "classification": "OBSERVED",
  "root_causes": [ { "kind": "INVENTORY_ALLOCATION_FAILED", "explanation": "Stock could not be allocated …" } ],
  "failure_chain": ["WEBHOOK_DELAYED", "ORDER_NOT_CONFIRMED", "INVENTORY_RESERVATION_EXPIRED",
                     "INVENTORY_ALLOCATION_FAILED", "FULFILLMENT_NOT_CREATED", "CUSTOMER_IMPACT"]
}
```

`GET /api/v1/impact/{id}` on the same journey reports the consequences in
three strictly-labelled lists — OBSERVED (records), DERIVED (deterministic
steps such as "a shipment could not be created"), POTENTIAL ("refund or
dispute risk … no refund has been recorded yet" — a signalled possibility,
never a fact) — plus the scope (MULTI_TRANSACTION when other orders share
the shortage SKU), the affected cohort with each member's own Part 5
outcome, and the transparent impact score.

## 13. Current limitations

- Outcome metrics on the dashboard (98.4% / 94.1% / 3.7% / 2.2%) remain
  **DEMO / PRE-INTELLIGENCE** estimates from `frontend/lib/demo-data.ts`;
  per-transaction outcomes on `/transactions/[id]` are computed in real
  time by the Part 5 engine from the seeded journeys. The dashboard's
  failure-pattern widget is still demo data; the standalone **/failures**
  and **/simulation** pages show real Part 6/7 engine output. Rolling the
  dashboard KPIs over the real engine output is a later milestone.
- The build environment has no live PostgreSQL, so migrations, seeding and
  validation were verified against SQLite; the schema is written for
  PostgreSQL (psycopg, JSONB variant, timestamptz) — run
  `alembic upgrade head` against a real instance before production use.
- Part 5 confidence is a **deterministic record-strength score**, not a
  calibrated statistical probability — it reflects how strong the
  supporting records are, and it makes no real-world predictive claim.
- The Outcome Engine never guesses: contradictory or insufficient records
  produce UNVERIFIABLE, and the compound-failure chain is classified as a
  business FAILED even though the payment was captured.
- Part 6 impact is deterministic and transparent: the impact score is an
  indexed severity summary with its formula returned in the payload — it
  is **not** a financial-loss estimate, not a prediction, and potential
  consequences are signalled possibilities, never facts.
- Part 7 simulations are deterministic scenario estimates, not predictions
  or guarantees: every result is labelled SIMULATED, interventions that
  cannot act report NOT_APPLICABLE / NOT_EFFECTIVE / NOT_SUPPORTED,
  remedies never fabricate stock, substitutes or deliveries, and the
  ranked comparison is not a recommendation.
- In the seed-42 dataset every shortage SKU ends with zero available
  stock, so ALTERNATIVE_INVENTORY truthfully reports NOT_EFFECTIVE there;
  an effective inventory remedy is demonstrated only by isolated
  fixtures.
- Cross-transaction impact is only detected through explicit shared
  identifiers — an `INVENTORY_OUT_OF_STOCK` record sharing a product SKU
  — so delivery/order-level cross-impact with no shared identifier is not
  inferred.
- Part 9 webhook ingestion is TEST MODE only: with no
  `RAZORPAY_WEBHOOK_SECRET` configured, deliveries are only accepted via
  the explicit `X-PAYSCAPE-DEMO: 1` header (in demo mode) and are
  recorded with `signature_verified=false` — strict HMAC verification
  applies the moment a secret is configured. The endpoint never performs
  real financial transactions.
- Part 8 decisions are **recommendations only**: approving or rejecting
  records the merchant's decision on the `decisions` row and never
  executes refunds, payments, messages or any external action. There is
  no autonomous execution anywhere in the system.
- With no LLM configured (the default), the Decision Agent uses the
  deterministic fallback; an OpenAI-compatible HTTP provider is
  supported behind the `DecisionLLMProvider` interface but is not
  exercised in this environment (no keys), and its output is always
  validated by code against the verified context before use.
- LLM reasoning is bounded by the verified context: it cannot invent
  evidence or choose unregistered actions, and it never sees hidden
  chain-of-thought — only the concise decision rationale is stored or
  shown.
- The Decision Agent depends on Parts 3–7 being available; if those
  engines cannot run, no decision is generated (the API returns 404/503
  rather than guessing).
- AI agents remain interface placeholders.
- Full details: `docs/limitations.md`.

## 14. Planned future modules

1. **Agents**: intent/evidence/outcome agents and the orchestrator over
   structured events.
2. **Action execution layer** — execute APPROVED decisions through real
   provider APIs (Razorpay refunds etc.) behind explicit operator
   confirmation; Part 9 deliberately stops at recording approval and
   webhook ingestion.
3. **Provider integrations** beyond Razorpay (other payment providers)
   via the same Part 3 adapter interface
   (`backend/app/ingestion/adapters/`).
4. **Dashboard KPIs** computed over the real per-transaction outcomes.
5. **Cross-merchant / pattern analytics** built on the Part 6/7 dataset
   detections (`GET /api/v1/failures`).

---

See `docs/` for the architecture and methodology behind these plans.
