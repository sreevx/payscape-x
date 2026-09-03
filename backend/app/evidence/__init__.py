"""Evidence Engine (Part 4).

Deterministically answers "what do we actually have evidence for?" over a
reconstructed journey. It never answers "did the business transaction
succeed?" — that belongs to the Outcome Engine (Part 5).

Pipeline (pure, deterministic):

    ReconstructedJourney + JourneyIntegrity + DomainContext
        -> EvidenceReport
"""