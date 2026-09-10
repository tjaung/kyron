from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, synonym

from server.core.database import Base


class SimulationConversation(Base):
    __tablename__ = "conversation"
    __table_args__ = (
        CheckConstraint("next_conversation IS NULL OR next_conversation <> conversation_id"),
        CheckConstraint("jsonb_typeof(context) = 'object'"),
        {"schema": "simulation"},
    )
    conversation_id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str]
    context: Mapped[dict] = mapped_column(JSONB)
    transcript = synonym("context")  # Compatibility for older integrations; contains context, never generated speech.
    is_used: Mapped[bool] = mapped_column(server_default=text("false"))
    next_conversation: Mapped[UUID | None] = mapped_column(ForeignKey(
        "simulation.conversation.conversation_id", deferrable=True, initially="DEFERRED"
    ))
