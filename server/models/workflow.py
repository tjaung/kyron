"""Versioned definitions are separate from observed workflow and replay results."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from server.core.database import Base


class ActionDefinition(Base):
    __tablename__ = 'actions'
    __table_args__ = (UniqueConstraint('code', 'version'), {'schema': 'kyron'})
    action_id: Mapped[UUID] = mapped_column(primary_key=True)
    code: Mapped[str]
    version: Mapped[int]
    name: Mapped[str]
    instructions: Mapped[str]
    actor: Mapped[str]
    timing: Mapped[str]
    result_fields: Mapped[dict] = mapped_column(JSONB)


class Rule(Base):
    __tablename__ = 'rules'
    __table_args__ = (UniqueConstraint('code', 'version'), {'schema': 'kyron'})
    rule_id: Mapped[UUID] = mapped_column(primary_key=True)
    code: Mapped[str]
    version: Mapped[int]
    name: Mapped[str]
    description: Mapped[str]


class RuleAction(Base):
    __tablename__ = 'rule_actions'
    __table_args__ = {'schema': 'kyron'}
    rule_id: Mapped[UUID] = mapped_column(ForeignKey('kyron.rules.rule_id'), primary_key=True)
    action_id: Mapped[UUID] = mapped_column(ForeignKey('kyron.actions.action_id'), primary_key=True)
    # Every action in a rule is required; display order never implies execution order.


class Workflow(Base):
    __tablename__ = 'workflows'
    __table_args__ = (UniqueConstraint('code', 'version'), {'schema': 'kyron'})
    workflow_id: Mapped[UUID] = mapped_column(primary_key=True)
    code: Mapped[str]
    version: Mapped[int]
    name: Mapped[str]
    description: Mapped[str]
    entry_rule_id: Mapped[UUID] = mapped_column(ForeignKey('kyron.rules.rule_id'))


class WorkflowStep(Base):
    __tablename__ = 'workflow_steps'
    __table_args__ = {'schema': 'kyron'}
    workflow_id: Mapped[UUID] = mapped_column(ForeignKey('kyron.workflows.workflow_id'), primary_key=True)
    rule_id: Mapped[UUID] = mapped_column(ForeignKey('kyron.rules.rule_id'), primary_key=True)
    # Each branch tests one declared action result; target is a rule UUID or a terminal outcome.
    branches: Mapped[list] = mapped_column(JSONB)


class WorkflowRun(Base):
    __tablename__ = 'workflow_runs'
    __table_args__ = {'schema': 'kyron'}
    run_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(ForeignKey('kyron.workflows.workflow_id'))
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey('kyron.conversation_record.id'))
    practice_id: Mapped[UUID] = mapped_column(ForeignKey('providers.practice.practice_id'))
    current_rule_id: Mapped[UUID] = mapped_column(ForeignKey('kyron.rules.rule_id'))
    status: Mapped[str] = mapped_column(default='active')
    observations: Mapped[list] = mapped_column(JSONB, default=list)
    completed_rules: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
