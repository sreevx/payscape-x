"""Outcome Engine (Part 5).

Deterministically answers "did the business transaction actually succeed?"
for one reconstructed transaction, classifying it as exactly one of
FULFILLED / AT_RISK / FAILED / UNVERIFIABLE.

The engine consumes the Part 3 journey, the Part 4 evidence report and the
Part 4 consistency report and runs an explicit, documented rule hierarchy
(see rules.py). It is fully deterministic — same inputs always produce the
same outcome, confidence, reasons and evidence references.

Core distinction: a successful payment is NOT a fulfilled business
transaction. FULFILLED is only assigned from a delivery-completed record;
FAILED is decided from business records (system failure markers, delivery
failure, cancellation after capture, allocation failure), never from the
payment status alone. AI reasons later; code verifies the current outcome.
"""