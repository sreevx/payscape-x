"""Event ingestion layer (Part 3).

Accepts events from existing synthetic TransactionEvents and from future
provider/webhook payloads through a common pipeline:

    raw payload → adapter → validate → normalize → correlate → persist

The pipeline is deterministic, idempotent where an idempotency key exists,
never silently discards an event, and contains zero AI reasoning. Provider
specifics live behind the adapter interface so real providers (e.g.
Razorpay webhooks) can be added later without touching the pipeline.
"""