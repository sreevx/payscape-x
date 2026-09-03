"""part 8: add decisions table (audit trail + human approval)

The Decision Agent must record every recommendation and its human-approval
lifecycle (PENDING / APPROVED / REJECTED). One row per transaction; the
`decision_id` is deterministic (uuid5 over the transaction id), so repeated
generation upserts the same row and never resets the approval status.

The table stores only verified facts and references (evidence ids, event
ids, the simulation used, the fallback rule) — never hidden chain-of-thought
and never credentials. Approving or rejecting only updates this row; the
application never executes the recommended action.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TS = sa.text("CURRENT_TIMESTAMP")


def _json() -> sa.JSON:
    """JSON column — JSONB on PostgreSQL, JSON everywhere else."""
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=False),
        sa.Column("transaction_id", sa.Uuid(), nullable=False),
        sa.Column("decision_source", sa.String(length=32), nullable=False),
        sa.Column("recommended_action", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decision_confidence", sa.Float(), nullable=False),
        sa.Column("evidence_confidence", sa.Float(), nullable=False),
        sa.Column("evidence_ids", _json(), nullable=False),
        sa.Column("event_ids", _json(), nullable=False),
        sa.Column("simulation_id", sa.Uuid(), nullable=True),
        sa.Column("alternatives", _json(), nullable=False),
        sa.Column("human_approval_required", sa.Boolean(), nullable=False),
        sa.Column("approval_status", sa.String(length=16), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", _json(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=_TS,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decisions_decision_id", "decisions", ["decision_id"], unique=True)
    op.create_index("ix_decisions_transaction_id", "decisions", ["transaction_id"])
    op.create_index("ix_decisions_approval_status", "decisions", ["approval_status"])
    op.create_index("ix_decisions_source", "decisions", ["decision_source"])
    op.create_index("ix_decisions_action", "decisions", ["recommended_action"])


def downgrade() -> None:
    op.drop_index("ix_decisions_action", table_name="decisions")
    op.drop_index("ix_decisions_source", table_name="decisions")
    op.drop_index("ix_decisions_approval_status", table_name="decisions")
    op.drop_index("ix_decisions_transaction_id", table_name="decisions")
    op.drop_index("ix_decisions_decision_id", table_name="decisions")
    op.drop_table("decisions")