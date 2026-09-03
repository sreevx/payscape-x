"""Decision entity — the Part 8 audit trail + human-approval record.

One row per transaction decision. `decision_id` is deterministic (uuid5 over
the transaction id), so regenerating the decision for the same transaction
upserts the same row and never resets the approval status.

The row records the recommendation, its source (LLM or deterministic
fallback), every traceable reference (evidence ids, event ids, the
simulation used, the fallback rule), the deterministic confidence, and the
human-approval lifecycle (PENDING -> APPROVED / REJECTED with an optional
rejection reason).

Approving or rejecting NEVER executes the action — Part 8 only records the
merchant's decision. The column names are snake_case; `metadata_` is the
JSON column (the project-wide convention to avoid shadowing the
SQLAlchemy `metadata` attribute).
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import DecisionAction, DecisionApprovalStatus, DecisionSource
from app.models.base import TimestampMixin, enum_type, uuid_pk_column


class Decision(TimestampMixin, Base):
    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = uuid_pk_column()
    # Deterministic: uuid5(namespace, f"payscape:decision:{transaction_id}").
    decision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, nullable=False, unique=True, index=True
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, nullable=False, index=True
    )
    decision_source: Mapped[DecisionSource] = mapped_column(
        enum_type(DecisionSource, "decision_source", length=32),
        nullable=False,
        index=True,
    )
    recommended_action: Mapped[DecisionAction] = mapped_column(
        enum_type(DecisionAction, "decision_action", length=32),
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decision_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    event_ids: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    # Deterministic simulation id the recommendation is based on (if any).
    simulation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    alternatives: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    human_approval_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    approval_status: Mapped[DecisionApprovalStatus] = mapped_column(
        enum_type(DecisionApprovalStatus, "decision_approval_status", length=16),
        nullable=False,
        default=DecisionApprovalStatus.PENDING,
        index=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )

    def __repr__(self) -> str:
        return (
            f"<Decision id={self.id} transaction={self.transaction_id} "
            f"action={self.recommended_action} status={self.approval_status}>"
        )


# Type helpers used by the service layer.
DecisionSourceValue = str
DecisionActionValue = str
DecisionApprovalValue = str
DecisionOptional = Optional[Decision]