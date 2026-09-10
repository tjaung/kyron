from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class Observation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action_id: UUID
    status: Literal['completed','failed','blocked','skipped']
    result: dict = Field(default_factory=dict)
    evidence: str = Field(min_length=1, max_length=10000)


class Observations(BaseModel):
    observations: list[Observation] = Field(max_length=10)


class NextAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    target: Literal['patient','insurance_agent','provider','pharmacy']
    objective: str = Field(min_length=5, max_length=1500)
    action_id: UUID


class PlannedAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['log','notification','message','call']
    target: Literal['practice','patient','provider','pharmacy','insurance_agent']
    description: str = Field(min_length=5, max_length=1000)
    workflow_code: Literal['new_prescription'] | None = None
    action_code: str | None = Field(default=None, max_length=100)


class IntakeReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    verified: bool | None = None
    contact_permission: bool | None = None
    identity_evidence: str = ''
    identity_turn_index: int | None = Field(default=None, ge=0)
    reason: str = ''
    requested_outcome: str = ''
    reason_evidence: str = ''
    reason_turn_index: int | None = Field(default=None, ge=0)
    proposed_actions: list[str] = Field(default_factory=list, max_length=8)
    plan_evidence: str = ''
    plan_turn_index: int | None = Field(default=None, ge=0)


class AnalysisOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    summary: str = Field(min_length=10, max_length=2000)
    overall_sentiment: Literal['positive','neutral','negative','mixed']
    reason_for_call: str = Field(min_length=3, max_length=1000)
    actions_needed: list[str] = Field(default_factory=list, max_length=30)
    next_action: NextAction | None = None
    selected_workflow: Literal['new_prescription'] | None = None
    routing_reason: str = Field(default='', max_length=1000)
    intake: IntakeReview | None = None
    planned_actions: list[PlannedAction] = Field(default_factory=list, max_length=8)


class AnalyzeRequest(BaseModel):
    turn_limit_reached: bool = False
    rerun: bool = False


