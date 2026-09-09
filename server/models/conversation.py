from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from server.core.database import Base


class ConversationRecord(Base):
    __tablename__ = "conversation_record"
    __table_args__ = {"schema": "kyron"}
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    practice_id: Mapped[UUID] = mapped_column(ForeignKey("providers.practice.practice_id"))
    patient_practice_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("patients.patient_practice.patient_practice_id")
    )
    prescription_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("clinical.prescription.prescription_id")
    )
    source_conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("simulation.conversation.conversation_id")
    )
    name: Mapped[str]
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(default="live")
    last_sequence: Mapped[int] = mapped_column(default=0)


class ConversationAnalysis(Base):
    __tablename__ = "conversation_analysis"
    __table_args__ = {"schema": "kyron"}
    analysis_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_record_id: Mapped[UUID] = mapped_column(
        ForeignKey("kyron.conversation_record.id"), unique=True
    )
    overall_sentiment: Mapped[str | None]
    reason_for_call: Mapped[str | None]


class ConversationTranscript(Base):
    __tablename__ = "conversation_transcript"
    __table_args__ = (
        UniqueConstraint("conversation_record_id", "turn_index"), {"schema": "kyron"},
    )
    transcript_id: Mapped[UUID] = mapped_column(primary_key=True)
    conversation_record_id: Mapped[UUID] = mapped_column(ForeignKey("kyron.conversation_record.id"))
    speaker: Mapped[str]
    transcript: Mapped[str] = mapped_column(default="")
    turn_index: Mapped[int]
    last_word_index: Mapped[int] = mapped_column(default=0)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    action: Mapped[UUID | None] = mapped_column(ForeignKey(
        "kyron.actions.action_id", name="transcript_action_fk", use_alter=True,
        deferrable=True, initially="DEFERRED",
    ), unique=True)


class Action(Base):
    __tablename__ = "actions"
    __table_args__ = {"schema": "kyron"}
    action_id: Mapped[UUID] = mapped_column(primary_key=True)
    analysis_id: Mapped[UUID] = mapped_column(ForeignKey("kyron.conversation_analysis.analysis_id"))
    transcript_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("kyron.conversation_transcript.transcript_id"), unique=True
    )
    action: Mapped[str]
    reason: Mapped[str]
    is_completed: Mapped[bool] = mapped_column(default=False)
    previous_action: Mapped[UUID | None] = mapped_column(ForeignKey("kyron.actions.action_id"), unique=True)
    next_action: Mapped[UUID | None] = mapped_column(ForeignKey("kyron.actions.action_id"), unique=True)


class ConversationEvent(Base):
    __tablename__ = "conversation_event"
    __table_args__ = (
        UniqueConstraint("conversation_record_id", "sequence"), {"schema": "kyron"},
    )
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    conversation_record_id: Mapped[UUID] = mapped_column(ForeignKey("kyron.conversation_record.id"))
    sequence: Mapped[int]
    data: Mapped[dict] = mapped_column(JSONB)
