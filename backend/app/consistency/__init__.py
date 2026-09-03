"""Consistency Engine (Part 4).

Deterministically evaluates business/process invariants over a
reconstructed journey and answers "do the observed records agree with each
other?" It never answers "did the customer ultimately receive the promised
business outcome?" — that belongs to the Outcome Engine (Part 5).

Critical rule: absence of evidence is not evidence of failure. Rules whose
inputs are missing return INSUFFICIENT_EVIDENCE or NOT_APPLICABLE, never
VIOLATION — unless an explicit rule establishes a contradiction.

Pipeline (pure, deterministic):

    ReconstructedJourney + DomainContext -> ConsistencyResult
"""