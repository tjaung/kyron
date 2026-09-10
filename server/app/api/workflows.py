from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from server.app.services.auth import require_auth, verify_origin
from server.app.services.workflows import checklist, record_result, advance
from server.core.database import get_session
from server.models.conversation import ConversationRecord
from server.models.workflow import Workflow, Rule, WorkflowStep, WorkflowRun
from server.schemas.auth import AuthSession

router = APIRouter(tags=['workflows'])


class StartRun(BaseModel):
    workflow_id: UUID
    conversation_id: UUID


class Result(BaseModel):
    action_id: UUID
    status: Literal['completed','failed','blocked','skipped']
    result: dict = Field(default_factory=dict)
    evidence: str = Field(default='', max_length=10000)


def get_run(session, run_id, auth, lock=False):
    query = select(WorkflowRun).where(WorkflowRun.run_id == run_id, WorkflowRun.practice_id == auth.practice.practice_id)
    if lock: query = query.with_for_update()
    run = session.scalar(query)
    if run is None: raise HTTPException(404, 'Workflow run not found')
    return run


def view(session, run):
    return {'run_id': run.run_id, 'workflow_id': run.workflow_id, 'conversation_id': run.conversation_id,
            'status': run.status, 'current_rule_id': run.current_rule_id,
            'completed_rules': run.completed_rules, 'checklist': checklist(session, run), 'observations': run.observations}


@router.get('/workflows')
def definitions(session: Session = Depends(get_session), auth: AuthSession = Depends(require_auth)):
    return [{'workflow_id': w.workflow_id,'code':w.code,'version':w.version,'name':w.name,'description':w.description,'entry_rule_id':w.entry_rule_id}
            for w in session.scalars(select(Workflow).order_by(Workflow.code,Workflow.version))]


@router.get('/workflows/{workflow_id}')
def definition(workflow_id: UUID, session: Session = Depends(get_session), auth: AuthSession = Depends(require_auth)):
    workflow = session.get(Workflow,workflow_id)
    if workflow is None: raise HTTPException(404,'Workflow not found')
    rules = []
    for step in session.scalars(select(WorkflowStep).where(WorkflowStep.workflow_id == workflow_id)):
        rule = session.get(Rule,step.rule_id)
        # A transient empty run exposes reusable definitions through the same checklist view.
        temporary = WorkflowRun(current_rule_id=rule.rule_id,observations=[])
        rules.append({'rule_id':rule.rule_id,'name':rule.name,'description':rule.description,
                      'actions':checklist(session,temporary),'branches':step.branches})
    return {'workflow_id':workflow.workflow_id,'name':workflow.name,'version':workflow.version,
            'entry_rule_id':workflow.entry_rule_id,'rules':rules}


@router.post('/workflow-runs', status_code=201, dependencies=[Depends(verify_origin)])
def start(payload: StartRun, session: Session = Depends(get_session), auth: AuthSession = Depends(require_auth)):
    conversation = session.scalar(select(ConversationRecord).where(ConversationRecord.id == payload.conversation_id,
        ConversationRecord.practice_id == auth.practice.practice_id))
    if conversation is None: raise HTTPException(404,'Conversation not found')
    workflow = session.get(Workflow,payload.workflow_id)
    if workflow is None: raise HTTPException(404,'Workflow not found')
    run = WorkflowRun(workflow_id=workflow.workflow_id,conversation_id=conversation.id,practice_id=auth.practice.practice_id,
        current_rule_id=workflow.entry_rule_id,created_at=datetime.now(timezone.utc))
    session.add(run); session.flush()
    result = view(session,run); session.commit(); return result


@router.get('/workflow-runs/{run_id}')
def read(run_id: UUID, session: Session = Depends(get_session), auth: AuthSession = Depends(require_auth)):
    return view(session,get_run(session,run_id,auth))


@router.post('/workflow-runs/{run_id}/results', dependencies=[Depends(verify_origin)])
def observe(run_id: UUID, payload: Result, session: Session = Depends(get_session), auth: AuthSession = Depends(require_auth)):
    run = get_run(session,run_id,auth,lock=True)
    record_result(session,run,payload.action_id,payload.status,payload.result,payload.evidence)
    result = view(session,run); session.commit(); return result


@router.post('/workflow-runs/{run_id}/advance', dependencies=[Depends(verify_origin)])
def progress(run_id: UUID, session: Session = Depends(get_session), auth: AuthSession = Depends(require_auth)):
    run = get_run(session,run_id,auth,lock=True)
    advance(session,run)
    result = view(session,run); session.commit(); return result
