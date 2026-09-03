# PAYSCAPE-X Limitations (Part 9)

## Deliberately not implemented

The architectural rules in the project brief are strict:

1. No AI agents (Rule 1).
2. No AI/stochastic simulations (Rule 4) — with one deliberate exception:
   **Part 7's Simulation Lab is fully deterministic and read-only**, a
   rules-based replay over the recorded journey whose every result is
   labelled SIMULATED. No LLM, no randomness, no autonomous action.
3. **Razorpay integration is TEST MODE only (Part 9).** The webhook
   endpoint accepts Razorpay TEST-MODE deliveries, verifies their
   signature (when a secret is configured) and passes them through the
   exact Part 3 pipeline — it never performs real financial transactions,
   and DEMO / SYNTHETIC data is always clearly separated from verified
   TEST-MODE deliveries.
4. No fake AI functionality (Rule 6).
5. No hardcoded secrets (Rule 7).
6. No business logic inside React components (Rule 8).
7. **No LLMs, embeddings, vector databases, AI-generated conclusions,
   recommendations, fraud detection, payment optimization, autonomous
   actions, or consequence prediction anywhere through Part 9** (the only
   LLM anywhere is the Part 8 Decision Agent's optional, validated,
   non-executing provider). Outcomes, evidence strengths, contradictions,
   gaps, consistency verdicts, failure chains, root causes, consequences
   and simulations are deterministic and explainable (`rule_id` on every
   finding). AI reasons; code verifies. Parts 5–9 add no reasoning of
   their own beyond explicit, auditable decision hierarchies — Part 6
   never predicts what happens next, Part 7 simulation results are
   scenario estimates (never predictions or guarantees), and Part 9
   webhook ingestion is record-only (it never transacts).
8. **Part 8's Decision Agent is the one intentional LLM exception — and it
   is strictly bounded.** The agent may reason only over the structured
   verified facts from Parts 3–7 (never raw records), may only pick one of
   the four registered actions, and every output is validated by code
   (registered action, real evidence/event/simulation ids, concise
   reason); invalid output falls back to the deterministic rule registry.
   Confidence is computed deterministically (LLM confidence is an
   explanation signal only), no hidden chain-of-thought is stored or
   shown, and approval only records the merchant's decision — Part 8
   never executes refunds, payments, messages or any external action.
   Without any API key (the default) the agent uses the deterministic
   fallback and no LLM is called at all.

Placeholder packages under `backend/app/{agents,rules}` define interfaces
only; every implementation method raises `NotImplementedError`. The Part 1
placeholder `backend/app/simulation/` is now the deterministic Simulation
Lab (Part 7); `backend/app/outcome/` is the Outcome Engine (Part 5);
`backend/app/failures/` and `backend/app/impact/` are the Compound Failure
and Consequence / Impact engines (Part 6); `backend/app/decision/` is the
AI Decision Agent (Part 8) with its deterministic fallback and optional
LLM provider; `backend/app/ingestion/adapters/razorpay.py` is the
Razorpay TEST-MODE webhook adapter (Part 9) feeding the existing Part 3
pipeline. The Part 1 graph primitives
(`backend/app/graph/base.py`) remain superseded by the deterministic
`backend/app/journey/graph.py`.

## Part 4 decisions that remain structural

- **Evidence strength is derived from records, never guessed.** Absent
  claims are reported only when a structural rule expects them (MISSING);
  otherwise they are simply not reported. No probability model, no
  heuristics — DIRECT / CORROBORATED / INDIRECT / MISSING / CONTRADICTED
  come from an explicit decision table (`app/evidence/strength.py`).
- **A missing event is NOT a consistency violation.** Rules whose inputs
  are absent return `INSUFFICIENT_EVIDENCE` (rule plausibly applies) or
  `NOT_APPLICABLE` (rule does not apply) — never `VIOLATION`, unless an
  explicit rule establishes a contradiction. Absence of evidence is never
  treated as evidence of failure.
- **Contradictions are recorded, not resolved.** `PAYMENT_CAPTURED` +
  `PAYMENT_FAILED` (and any future pair) produces a
  `PAYMENT_FAILED_SHOULD_NOT_BE_CAPTURED` VIOLATION and CONTRADICTED
  evidence on both sides; neither event is deleted and neither is
  preferred.
- **`overall_integrity` is record agreement only.** CONSISTENT /
  INCONSISTENT / INSUFFICIENT_EVIDENCE describe whether the observed
  records agree — they are never rendered or interpreted as business
  outcomes.
- **Evidence gaps phrase observations.** Output says "X present but Y not
  observed" — never "shipment failed" or "transaction failed".

## Outcome intelligence

- **Part 5 outcomes are deterministic classifications of the recorded
  journey, NOT predictions.** `FULFILLED / AT_RISK / FAILED / UNVERIFIABLE`
  and the confidence figure describe what the records show under an
  explicit rule hierarchy (`app/outcome/rules.py`). They carry no
  real-world predictive claim, and no historical ML has been trained.
- **Confidence is a deterministic score** derived from evidence strength,
  corroboration, contradictions, consistency violations, and lifecycle
  completeness — it is not a probability of any future event. With
  insufficient evidence, confidence correctly falls toward 0.5–0.6 rather
  than manufacturing certainty.
- **Payment success is not business success.** The engine reads the whole
  journey: the synthetic COMPOUND_FAILURE transaction is classified FAILED
  (inventory allocation definitively failed, fulfillment never created)
  even though its payment succeeded — that is the central demonstration of
  PAYSCAPE-X. Conversely, payment badge "FAILED" (e.g. CONTRADICTORY_EVENT
  with `PAYMENT_FAILED` + `PAYMENT_CAPTURED`) yields business outcome
  UNVERIFIABLE, not automatic FAILED.
- **AT_RISK is deliberately narrow.** It is used only when a recoverable
  operational problem exists (e.g. webhook delay with inventory expiry);
  incomplete data is never AT_RISK — it is UNVERIFIABLE.
- **Contradictory critical state forces UNVERIFIABLE.** Where both
  `PAYMENT_CAPTURED` and `PAYMENT_FAILED` are present, no business outcome
  is asserted with certainty.
- Dashboard outcome metrics (98.4% / 94.1% / 3.7% / 2.2%) are still **DEMO
  / PRE-INTELLIGENCE** estimates from `frontend/lib/demo-data.ts`, clearly
  labelled in the UI. They are NOT computed from the seeded journeys.
- Evidence-gap heuristics (missing allocation / fulfillment events) and
  the marker list for definitive business failure are tuned to the
  synthetic registry (`app/outcome/rules.py` is the single extension
  point). New providers may require new markers or reasons.

## Part 6 decisions that are intentional

- **Compound failure is a strict, conservative claim.** A compound failure
  is detected only when the Part 5 outcome is FAILED AND at least two
  chain nodes span at least two distinct promise stages. A lone
  `PAYMENT_FAILED` or order cancellation is reported as a single-stage
  business failure (`SINGLE_STAGE_BUSINESS_FAILURE`, severity MEDIUM) —
  never dressed up as a compound chain. A duplicate webhook alone is never
  a compound failure, and FULFILLED / AT_RISK / UNVERIFIABLE journeys are
  always reported undetected with an explicit reason code.
- **The engine never invents causal chains from uncertainty.** MISSING_EVENT
  and CONTRADICTORY_EVENT journeys (both UNVERIFIABLE) produce no failure
  chain and no consequences — absence of evidence and contradictory records
  are preserved, not resolved into a story.
- **The root cause is not the earliest event.** Root-cause selection uses
  an explicit priority table over OBSERVED business-stage nodes
  (payment failure > inventory allocation/expiry > fulfillment > delivery
  > order > webhook delay). In the compound scenario the webhook delay is
  chronologically first but the root cause is `INVENTORY_ALLOCATION_FAILED`;
  the delay is kept in the chain as a contributing factor.
- **OBSERVED vs DERIVED vs POTENTIAL is never blurred.** Chain nodes and
  consequences carry one of the three labels. OBSERVED = stated by a
  record; DERIVED = follows deterministically from records (a documented
  absence such as "fulfillment shipped but no shipment ever appeared"); a
  DERIVED node is never used as a root cause. **POTENTIAL consequences are
  NOT predictions** — they are emitted only when a customer signal exists
  (complaint or problem message) and no refund is recorded, they are
  discounted in scoring, and the UI renders them visually distinct with an
  explicit "not an observed fact" note.
- **Consequences are only asserted for FAILED outcomes.** FULFILLED,
  AT_RISK and UNVERIFIABLE transactions report no consequences and an
  impact score of 0 — impact is never invented where the records cannot
  establish a business failure.
- **Cross-transaction impact requires an explicit shared identifier.** The
  engine only links transactions whose `INVENTORY_OUT_OF_STOCK` records
  share a product SKU. No fuzzy matching, no "probably also affected"
  inference — a cohort member is listed only when its own record stream
  shows the shared shortage (impact = OBSERVED).
- **The impact score is a transparent index, not a prediction and not a
  financial-loss estimate.** Its formula (severity base + observed /
  derived / potential weights + multi-transaction term, capped at 100) is
  documented in `docs/architecture.md` and returned component-by-component
  in the payload (`score_components`), so every point is auditable.
- **Severity uses an explicit ladder, not string ordering.** LOW < MEDIUM <
  HIGH < CRITICAL; a naive alphabetical `max()` would rank MEDIUM above
  HIGH, which is why Part 6 computes severity by ladder index. Compound
  chains reach CRITICAL at ≥4 distinct stages (or ≥3 with a customer
  complaint); MULTI_TRANSACTION scope raises impact severity one notch.
- **Deterministic ids throughout.** `compound_failure_id`, node/edge/root
  ids, `impact_id` and consequence ids are uuid5 over the transaction id,
  so repeated runs — across processes and databases — yield identical
  output.

## Part 8 decisions that are intentional

- **Part 8 is REASON → RECOMMEND → WAIT FOR HUMAN, never execution.**
  Approving or rejecting a decision updates the `decisions` row
  (PENDING → APPROVED / REJECTED with an optional reason) and nothing
  else. There is no code path that executes refunds, payments, messages
  or external provider actions from an approved decision — that is a
  later part by design.
- **The agent reasons only over verified facts.** The `DecisionContext` is
  built from the real Parts 3–7 outputs; the LLM (when configured) sees
  only that structured context, so it has no path to invent evidence,
  events, amounts, customers or simulation results. Every claimed
  evidence id / event id must exist in the verified context and every
  simulation reference must be one that actually ran.
- **The closed registry is enforced.** Only DO_NOTHING /
  RECOVER_ROOT_CAUSE / REFUND_OR_CONTAIN / HUMAN_REVIEW can ever be
  recommended — by the LLM or by the fallback. An LLM that returns an
  unregistered action is rejected and the deterministic fallback is used.
- **The deterministic fallback is the safe default.** With
  `DECISION_LLM_PROVIDER=none` (default) the agent runs 8 documented
  rules over the verified facts and produces the same recommendation for
  the same database state every time; it never guesses a remedy the
  records cannot support (recovery requires a Part 7 simulation that
  actually resolved a failure; containment requires a recorded
  customer-impacting failure and an applicable refund simulation).
- **Confidence never comes from the LLM.** `decision_confidence` is
  always computed deterministically from the outcome confidence, the
  mean supporting-evidence confidence and the consistency status
  (bounded 0.10–0.99). An LLM confidence value is kept only as an
  explanation signal (`metadata.llm_confidence_signal`) and never
  influences the system confidence.
- **No hidden chain-of-thought.** Only the concise decision rationale is
  persisted and shown; provider failures / rejections are summarised in
  `metadata.provider_note` (e.g. "hallucinated evidence ids: …") without
  exposing private reasoning.
- **Parts 5–7 remain the sole authorities.** The Decision Agent reads the
  outcome, failure/impact and simulation results and never recalculates,
  mutates or overrides them; a decision cannot change what the evidence
  engines concluded.
- **Deterministic, idempotent persistence.** `decision_id` is uuid5 over
  the transaction id, so repeated generation upserts the same row and
  never resets the approval status; repeated runs with the same database
  state produce identical recommendations.

## Part 9 decisions that are intentional

- **Webhook ingestion is record-only.** `POST /api/v1/webhooks/razorpay`
  verifies the delivery (or explicitly flags it as demo), records the raw
  `Webhook` row and passes the canonical events through the Part 3
  pipeline. It NEVER initiates refunds, captures, cancellations, customer
  messages or any external provider call — real financial execution
  remains a later part, and the system still stops at AI RECOMMENDATION →
  HUMAN APPROVAL (records only).
- **Signature verification is environment-configured and never fake.**
  With `RAZORPAY_WEBHOOK_SECRET` set, valid signatures are accepted and
  invalid or missing signatures are rejected (400). With no secret
  configured, the endpoint only accepts explicit demo-mode deliveries
  (`X-PAYSCAPE-DEMO: 1` + `DEMO_MODE=true`) and records
  `signature_verified=false` — an unverified delivery is never presented
  as verified. The secret is never hardcoded or logged.
- **Idempotency is inherited from Part 3.** The same provider event id
  delivered twice produces DUPLICATE ingestion results and a
  DUPLICATE-status webhook row; zero duplicate canonical events are ever
  persisted.
- **Correlation is explicit, never fuzzy.** Payment linking uses only the
  Razorpay payment id. A webhook whose payment cannot be found is
  preserved as an ORPHAN in the response and nothing is persisted — the
  event is never invented into a transaction.
- **Unknown events are preserved, not guessed.** A Razorpay event type
  outside the supported set is recorded (delivery + webhook row) with the
  canonical event marked UNKNOWN — never dropped, never auto-classified.

## Part 7 decisions that are intentional

- **Simulation results are SIMULATED, never facts.** Every intervention
  result carries `status = SIMULATED` and is labelled a scenario estimate
  in the API and the UI. The lab replays over a doctored in-memory journey
  view and re-runs the existing Part 5 outcome rules; nothing is
  persisted, and no payment / order / inventory / refund / webhook record
  is ever modified (read-only, no external calls).
- **Interventions must be able to act.** An intervention whose
  prerequisites are not met reports `NOT_APPLICABLE` / `NOT_EFFECTIVE` /
  `NOT_SUPPORTED` with an explicit reason instead of pretending. The lab
  never silently simulates an impossible action, never invents
  alternative stock, and never fabricates substitute products.
- **Remedies never fabricate delivery.** When the records contain no
  delivery, a successful simulation resolves the blocked stages but the
  simulated outcome honestly stays UNVERIFIABLE (or AT_RISK) — it is never
  upgraded to FULFILLED just because the intervention "worked".
- **Uncertainty is not simulated away.** MISSING_EVENT and
  CONTRADICTORY_EVENT journeys (UNVERIFIABLE) produce no invented recovery
  possibilities, and DO_NOTHING is a control whose replay leaves the
  baseline unchanged.
- **The impact delta is a simulated comparison, not money saved.**
  `delta = simulated − baseline` (negative = improvement) compares two
  deterministic scores and is never labelled as financial loss, a refund
  recommendation or a forecast.
- **No recommendation engine.** The comparison endpoint ranks
  interventions (impact reduction, then fewer remaining failures, then
  fewer assumptions) for the operator to inspect; the UI highlights the
  "best simulated result" — never a recommendation — and no action is ever
  taken autonomously.
- **Deterministic ids throughout.** `simulation_id` and all references are
  uuid5 over the transaction (and intervention), so identical database
  state + identical intervention → byte-identical JSON across runs and
  processes.

## Known limitations

**Database**
- The build environment had no live PostgreSQL and no Docker, so
  migrations, seeding and validation were verified against SQLite. The
  schema is written for PostgreSQL — psycopg 3, UUID keys, `JSONB`
  variants, `timestamptz` — but it has NOT been exercised against a real
  PostgreSQL server. Run `alembic upgrade head`, `python -m app.seed` and
  `python -m app.seed --validate` against a real instance before relying on
  it (see README).
- Tables are only created via migrations; nothing runs `create_all` at
  application startup.
- Parts 4–9 add **no tables and no migration** — evidence, consistency,
  outcomes, failure chains, impact, simulations and Razorpay webhook
  ingestion are computed deterministically from the existing Part 2/3
  records (`transaction_events` + the payment's domain rows, including the
  Part 2 `webhooks` table for raw delivery audit). Existing databases need
  no schema change to serve those endpoints. Part 8 adds exactly one table
  — `decisions` (migration `0004`) — to persist the decision audit trail
  and the human-approval status; everything else about a decision is
  computed.

**Synthetic data**
- Data is synthetic and deterministic (seed 42 default): NovaCart
  Commerce, 100 `@example.in` customers, 30 products, 150 journeys, 2,170
  unified events. Nothing is real merchant or payment data — no PII, no
  card numbers.
- Scenario counts are fixed by `backend/app/synthetic/scenarios.py`
  (70/15/10/10/10/10/10/5/5/5). Other distributions need a code change or a
  different seed (which still follows the same ratios).
- The compound-failure timeline intentionally contains a late `WEBHOOK_
  RECEIVED` followed by `WEBHOOK_DELAYED` / `ORDER_NOT_CONFIRMED`; that
  ordering is the generated story and is asserted by tests.
- Refund-flow journeys lack `INVENTORY_RESERVED` / `FULFILLMENT_CREATED`
  (refunded before allocation) — the resulting gaps/insufficient evidence
  are honest structural observations, not verdicts.
- Cross-transaction impact in the seed data comes from three products that
  open with zero stock (NC-0006 / NC-0013 / NC-0021): 15 of the 25
  detected compound failures share those SKUs across 4–6 transactions.
  Other scenario mixes may produce different cohort sizes.

**Engines**
- The Razorpay webhook adapter supports a deliberately small event set
  (`payment.created/authorized/captured/failed`, `refund.created/
  processed/failed`). Additional Razorpay event types (e.g. `payment.
  pending`, `order.paid`) would need aliases in
  `app/ingestion/normalizer.py` and handling in
  `app/ingestion/adapters/razorpay.py`; anything unsupported is preserved
  and marked UNKNOWN rather than dropped.
- Signature verification has not been exercised against Razorpay's live
  test-mode dashboard (no credentials in this environment); the HMAC
  scheme and constant-time comparison are covered by unit tests with
  locally computed signatures.
- A webhook whose payment cannot be linked is reported as an ORPHAN and
  is not persisted (the Part 2 `webhooks` table requires a payment id) —
  the raw payload is returned in the response for audit but not stored.
- Corroboration is limited to the record shapes the synthetic generator
  produces (payment rows, webhook rows, inventory/fulfillment/shipment/
  delivery ledgers, refunds, messages). A real provider that expresses the
  same facts differently may need a new corroborator — the claim registry
  in `app/evidence/collector.py` is the single place to add one.
- Evidence, outcomes, failure chains and impact are computed per payment
  (the transaction id used by `/api/v1/transactions`), matching Part 3
  reconstruction. Order-level journeys that split across multiple payments
  are a later consideration.
- Amount comparisons use recorded numeric values; float/decimal drift
  across providers would need an explicit epsilon policy (the synthetic
  dataset uses exact `Decimal` values).
- The 16 consistency rules, the 11 outcome rules, the chain-node/edge
  registries (`app/failures/rules.py`) and the consequence rules
  (`app/impact/engine.py`) are the documented registries; the engines never
  invent new invariants at runtime. Registry changes are code changes.
- Failure-chain node detection is event-registry-bound: a provider that
  reports the same problem with different event types needs a new node
  kind in `app/failures/rules.py`. Contradictory journeys and journeys that
  fail with no chain-node record produce undetected results by design.
- Cross-transaction impact is keyed only to `INVENTORY_OUT_OF_STOCK` SKU
  sharing. Delivery-level or order-level cross-impact has no shared
  identifier in the current dataset and is deliberately not inferred.
- The `/failures` dataset list deep-analyzes only payments that carry a
  FAILED-capable event marker (mirroring the Part 5 rule registry), but it
  is still a full pass over that subset; fine at the seeded scale, worth
  revisiting for large production datasets. Cohort-member outcome
  computation is bounded by a documented cap of 25 members per request.
- The impact score is a deterministic index, not a calibrated metric: its
  weights are engineering choices documented in `docs/architecture.md`, and
  it carries no real-world predictive or financial meaning.
- Simulation is bound to what the records can deterministically support.
  In the seed-42 dataset every shortage SKU ends with `available = 0`, so
  ALTERNATIVE_INVENTORY truthfully reports NOT_EFFECTIVE there; an
  effective inventory remedy is demonstrated only by isolated fixtures
  that record stock. RETRY_FULFILLMENT resolves only when the blocking
  condition is removable, remedies never fabricate deliveries (simulated
  outcomes without a recorded delivery stay UNVERIFIABLE / AT_RISK), and
  the lab never feeds back into the real transaction.
- The Decision Agent inherits every Part 3–7 limitation: it is only as
  good as the verified context, so a journey the evidence engines cannot
  classify produces HUMAN_REVIEW rather than a guessed action. Seed-42
  decisions: inventory_failure → HUMAN_REVIEW (no recorded stock remedy),
  delivery_failure and compound_failure → REFUND_OR_CONTAIN (customer
  impact), payment_failed and refund_flow → DO_NOTHING (no capture /
  containment already complete).
- The OpenAI-compatible HTTP provider is implemented but not exercised in
  this build environment (no API keys, no network); its behaviour is
  covered by unit tests through injected fake providers, and the
  deterministic fallback is the always-on safe path.
- LLM reasoning is bounded by the context builder: it cannot reference
  anything outside the verified facts, so recommendations never carry
  information the evidence engines did not produce. If the Parts 3–7
  engines cannot run, no decision is generated (404/503) rather than
  guessing.

**Frontend**
- `/transactions`, `/transactions/[id]`, `/events`, `/failures` and
  `/simulation` read the real backend dataset; `/transactions/[id]` renders
  the pipeline narrative strip (PAYMENT → JOURNEY → EVIDENCE →
  CONSISTENCY → OUTCOME → FAILURE → IMPACT → SIMULATION → AI DECISION →
  HUMAN APPROVAL) plus the reconstructed JOURNEY, EVIDENCE, CONSISTENCY,
  OUTCOME, COMPOUND FAILURE, CONSEQUENCES / IMPACT, SIMULATION LAB and AI
  DECISION sections from the real Part 6/7/8 APIs (the AI DECISION
  section includes the APPROVE / REJECT workflow, which records the
  merchant's decision only). The dashboard's investigations,
  failure-pattern widget and activity feed remain demo placeholders (the
  standalone /failures and /simulation pages are real engine data). There
  is no webhook-ingestion UI: Razorpay TEST-MODE deliveries are exercised
  through the API (curl / the /docs playground) so ingested events join
  the journey visible on the existing transaction detail page.
- The journey graph is rendered from the backend's deterministic positions
  with an SVG spine (PRECEDES) plus TRIGGERS/DERIVED_FROM arcs — React Flow
  was not installed and was deliberately not added. The Part 6 failure
  chain renders as a deterministic list with relationship edges (no graph
  library).
- The event explorer's first page is capped at 200 transactions / 50
  events per request; deeper pagination UI for transactions arrives with a
  later part.
- The command palette (⌘K) is not wired yet.

## Environment

- Secrets: only `.env.example` files ship; real credentials belong in local
  `.env` files which are git-ignored.
- The health endpoint reports `"database": "unavailable"` honestly when the
  database is unreachable; the UI shows *Backend Unavailable* in that case —
  an intended fallback, not a defect.
