"""Journey reconstruction (Part 3).

Reconstructs the canonical chronological journey for one transaction
(payment-level) from the unified TransactionEvent stream.

THE RULE: reconstruction describes what happened; it never decides what
should have happened. No business-outcome classification, no business-state
correctness rules, no repair of history. Raw events and timestamps are never
modified. Duplicate, delayed, missing, contradictory, out-of-order and
unknown events are preserved exactly as recorded.
"""