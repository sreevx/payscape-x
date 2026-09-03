"""Ingestion adapters.

An adapter translates one raw source representation into a canonical event.
Provider-specific logic stays inside adapters; the pipeline never sees raw
provider formats.
"""

from app.ingestion.adapters.base import EventAdapter, RawEventAdapter
from app.ingestion.adapters.razorpay import RazorpayWebhookAdapter
from app.ingestion.adapters.synthetic import SyntheticAdapter

__all__ = [
    "EventAdapter",
    "RawEventAdapter",
    "RazorpayWebhookAdapter",
    "SyntheticAdapter",
]