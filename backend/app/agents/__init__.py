"""Agent layer — placeholder only.

Part 1 deliberately implements NO agents (Rule 1). This package defines the
interfaces later parts will implement:

- intent_agent    — reconstruct customer intent from the journey
- evidence_agent  — collect and validate structured events
- outcome_agent   — classify FULFILLED / AT_RISK / FAILED / UNVERIFIABLE
- decision_agent  — recommend actions for human approval
- orchestrator    — coordinates agents along the journey

Every agent consumes structured TransactionEvent records (Rule 10).
"""