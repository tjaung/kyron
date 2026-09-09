from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from server.core.database import Base


class SimulationConversation(Base):
    __tablename__ = "conversation"
    __table_args__ = (
        CheckConstraint("next_conversation IS NULL OR next_conversation <> conversation_id"),
        CheckConstraint("jsonb_typeof(transcript) = 'object'"),
        {"schema": "simulation"},
    )
    conversation_id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str]
    transcript: Mapped[dict] = mapped_column(JSONB)
    is_used: Mapped[bool] = mapped_column(server_default=text("false"))
    next_conversation: Mapped[UUID | None] = mapped_column(ForeignKey(
        "simulation.conversation.conversation_id", deferrable=True, initially="DEFERRED"
    ))
