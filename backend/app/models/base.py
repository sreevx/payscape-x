"""Shared model building blocks."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column


def uuid_pk_column():
    """Primary-key column: UUID with a Python-side default (portable)."""
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def enum_type(enum_cls: type, name: str, length: int = 32):
    """Portable Enum column type.

    Stored as VARCHAR(length) + CHECK on both PostgreSQL and SQLite
    (`native_enum=False`), so migrations and isolated tests share one DDL
    shape. Python-level values are enforced by the enum class itself.
    """
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        name=name,
        validate_strings=True,
    )


class TimestampMixin:
    """Adds `created_at` / `updated_at` columns to a model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CreatedAtMixin:
    """Adds only a `created_at` column to a model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )