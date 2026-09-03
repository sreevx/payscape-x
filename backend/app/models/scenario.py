"""ScenarioInstance entity.

One row per generated transaction journey, recording which synthetic
scenario produced it. This makes every journey traceable and reproducible:
same seed → same scenario instances → same correlations.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, JSON, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import ScenarioType
from app.models.base import CreatedAtMixin, enum_type, uuid_pk_column


class ScenarioInstance(CreatedAtMixin, Base):
    __tablename__ = "scenario_instances"

    id: Mapped[uuid.UUID] = uuid_pk_column()
    # Unique journey correlation, shared by every event of this journey.
    correlation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, nullable=False, unique=True, index=True
    )
    scenario_type: Mapped[ScenarioType] = mapped_column(
        enum_type(ScenarioType, "scenario_type", length=32),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # JSON on SQLite, JSONB on PostgreSQL. Seed, merchant, journey index…
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )

    def __repr__(self) -> str:
        return (
            f"<ScenarioInstance id={self.id} type={self.scenario_type} "
            f"correlation={self.correlation_id}>"
        )