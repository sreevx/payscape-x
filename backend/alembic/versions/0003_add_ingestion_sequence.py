"""part 3: add ingestion_sequence to transaction_events

The ingestion-order requirement needs a monotonic per-row insertion
sequence. `created_at` is not reliable for this: it is server-side
second-precision `CURRENT_TIMESTAMP`, so a bulk load (or any two events in
the same transaction) ties, and the id tiebreak is a hash-based UUID that
does not reflect insertion order.

`ingestion_sequence` is assigned at persist time (generator append order
for synthetic data, next-value assignment for real ingestion) and is the
authoritative order the journey reconstruction layer compares against
event timestamps to detect out-of-order ingestion.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default keeps existing rows valid (sequence 0); freshly seeded
    # data always sets an explicit sequence.
    op.add_column(
        "transaction_events",
        sa.Column(
            "ingestion_sequence",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_transaction_events_ingestion_sequence",
        "transaction_events",
        ["ingestion_sequence"],
    )


def downgrade() -> None:
    # Batch mode: plain ALTER on PostgreSQL, copy-and-move on SQLite.
    with op.batch_alter_table("transaction_events") as batch_op:
        batch_op.drop_index("ix_transaction_events_ingestion_sequence")
        batch_op.drop_column("ingestion_sequence")