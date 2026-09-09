from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    practice_id: UUID
    patient_practice_id: UUID | None = None
    prescription_id: UUID | None = None
    source_conversation_id: UUID
    start_time: AwareDatetime
    name: str | None = Field(default=None, max_length=200)


class EventBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sequence: int = Field(ge=1)
    occurred_at: AwareDatetime


class TranscriptStarted(EventBase):
    type: Literal["transcript.started"]
    transcript_id: UUID
    turn_index: int = Field(ge=0)
    speaker: str = Field(min_length=1, max_length=100)


class TranscriptWord(EventBase):
    type: Literal["transcript.word"]
    transcript_id: UUID
    word_index: int = Field(ge=1)
    delta: str = Field(min_length=1, max_length=10000)


class TranscriptCompleted(EventBase):
    type: Literal["transcript.completed"]
    transcript_id: UUID


class SimulatedAction(EventBase):
    type: Literal["action.simulated"]
    action_id: UUID
    transcript_id: UUID | None
    action: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=5000)
    simulated: Literal[True]


class ConversationEnded(EventBase):
    type: Literal["conversation.ended"]


class ReplayCompleted(EventBase):
    type: Literal["replay.completed"]


ConversationEvent = Annotated[Union[
    TranscriptStarted, TranscriptWord, TranscriptCompleted, SimulatedAction,
    ConversationEnded, ReplayCompleted,
], Field(discriminator="type")]
