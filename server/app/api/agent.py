"""Simulator-only model tools, analysis, and persisted continuation decisions."""
import json
import logging
from simulator.debug_logging import log
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from server.app.services.auth import require_simulator
from server.app.services import agent
from server.app.crud.conversations import lock_event_writer
from server.app.api.simulations import simulator_request
from server.core.database import get_session
from server.models.conversation import ConversationAnalysis, ConversationRecord, ConversationTranscript, ActionTask
from server.models.workflow import Workflow
from server.app.services import analysis_model, action_plan
from server.schemas.agent import PlannedAction
from server.schemas.agent import Observations, AnalysisOutput, AnalyzeRequest
from simulator.local_model import LocalModel

router = APIRouter(prefix='/conversations', tags=['agent'], dependencies=[Depends(require_simulator)])
MAX_CALLS = 4


@router.post('/{conversation_id}/agent-context')
def get_context(conversation_id: UUID, session: Session = Depends(get_session)):
    lock_event_writer(session)
    record, run = agent.runtime(session,conversation_id)
    if run is None:
        run = agent.start_run(session,record)
    log('workflow.context.loaded', conversation_id=str(conversation_id), source_conversation_id=str(record.source_conversation_id), workflow_status=run.status)
    result = agent.context(session,record,run)
    session.commit()
    return result


@router.post('/{conversation_id}/observations')
def observations(conversation_id: UUID, payload: Observations, session: Session = Depends(get_session)):
    lock_event_writer(session)
    record, run = agent.runtime(session,conversation_id)
    if run is None: raise HTTPException(409,'Start the workflow first')
    try:
        result = agent.observe(session,record,run,payload.observations)
    except HTTPException as error:
        log('workflow.observations.rejected', level=logging.WARNING, conversation_id=str(conversation_id),
            status_code=error.status_code, action_ids=[str(o.action_id) for o in payload.observations])
        raise
    log('workflow.observations.saved', conversation_id=str(conversation_id), workflow_status=run.status,
        observation_count=len(payload.observations))
    session.commit()
    return result


def saved_analysis(session, conversation_id):
    return session.scalar(select(ConversationAnalysis).where(ConversationAnalysis.conversation_record_id == conversation_id))


@router.post('/{conversation_id}/analyze')
def analyze(conversation_id: UUID, payload: AnalyzeRequest, session: Session = Depends(get_session)):
    log('analysis.started', conversation_id=str(conversation_id), turn_limit_reached=payload.turn_limit_reached)
    # Per-conversation lock makes retries idempotent without blocking other event streams.
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:id, 0))'), {'id': str(conversation_id)})
    record, run = agent.runtime(session,conversation_id)
    analysis = saved_analysis(session,conversation_id)
    if analysis.analyzed_at and not payload.rerun:
        if not analysis.decision: return decide(session,conversation_id)
        return {'decision':analysis.decision, 'next_action':analysis.next_action}
    if record.status == 'live' or record.end_time is None:
        raise HTTPException(409,'Finish or stop the call before analysis')
    if payload.rerun:
        if analysis.metrics and analysis.metrics.get('failure') == 'cancelled_by_user':
            raise HTTPException(409,'Cancelled conversations cannot launch more work')
        record.status='processing'
        if run and run.status=='failed': run.status='active'
    elif record.status not in ('ended','processing'):
        raise HTTPException(409,'End the call before analysis')
    if run is None: run=agent.start_run(session,record)
    turns = session.scalars(select(ConversationTranscript).where(ConversationTranscript.conversation_record_id == record.id).order_by(ConversationTranscript.turn_index)).all()
    if not any(turn.transcript.strip() for turn in turns):
        raise HTTPException(409,'There is no recorded transcript to analyze')
    progress = agent.state(session,run)
    model = LocalModel(output_tokens=3600)
    model.timeout=min(model.timeout,180)  # Three attempts fit inside the simulator request deadline.
    catalog=[{'code':workflow.code,'description':workflow.description} for workflow in session.scalars(select(Workflow).where(Workflow.code!='patient_intake')).all()]
    try:
        output=analysis_model.evaluate(model,[{'speaker':t.speaker,'text':t.transcript} for t in turns],progress,catalog)
    except Exception as error:
        log('analysis.failed', level=logging.ERROR, exc_info=True, conversation_id=str(conversation_id))
        if hasattr(error, 'errors'):
            log('analysis.validation.failed', level=logging.ERROR, conversation_id=str(conversation_id),
                issues=[{'type':item['type'], 'field':item['loc']} for item in error.errors()])
        fail_record(session,conversation_id,'analysis_failed')
        raise HTTPException(502,'Local model analysis failed; conversation is marked failed. Check Ollama and model availability.') from error
    lock_event_writer(session)
    session.refresh(record)
    session.refresh(analysis)
    if record.status == 'failed':
        return {'decision':'failed','next_action':None}
    analysis_model.recover_intake(session,record,run,output.intake)
    progress=agent.state(session,run)
    existing_child=session.scalar(select(ConversationRecord).where(ConversationRecord.parent_conversation_id==record.id))
    old_next=analysis.next_action
    analysis.decision=None
    analysis.summary = output.summary
    analysis.overall_sentiment = output.overall_sentiment
    analysis.reason_for_call = output.reason_for_call
    analysis.actions_needed = output.actions_needed
    analysis.next_action = output.next_action.model_dump(mode='json') if output.next_action else None
    plans=list(output.planned_actions)
    for plan in plans:
        if plan.kind=='call' and not plan.workflow_code:
            plan.workflow_code=output.selected_workflow
    action_plan.save(session,analysis,plans)
    analysis.analyzed_at = datetime.now(timezone.utc)
    analysis.model = model.name
    latest = {(o['rule_id'],o['action_id']):o for o in run.observations}
    valid = [o for o in latest.values() if o['status']=='completed' and not o['missing_fields'] and not o['invalid_fields']]
    analysis.metrics = {'turn_count':len(turns), 'word_count':sum(len(t.transcript.split()) for t in turns),
        'duration_seconds':(record.end_time-record.start_time).total_seconds(),
        'completed_rules':len(run.completed_rules),'observed_actions':len(latest),'validated_actions':len(valid),
        'outstanding_action_ids':[i['action_id'] for i in progress['checklist'] if not i['ready']],
        'workflow_outcome':run.status,'turn_limit_reached':payload.turn_limit_reached,
        'selected_workflow':output.selected_workflow,'routing_reason':output.routing_reason,
        'expected_workflow_match':output.selected_workflow=='new_prescription' if not record.parent_conversation_id else None}
    if existing_child:
        analysis.next_action=old_next; analysis.decision='continue'; record.status='continued'
    else:
        record.status = 'processing'
    session.commit()  # Persist all metrics before making a continuation decision.
    log('analysis.saved', conversation_id=str(conversation_id), turn_count=len(turns),
        validated_actions=len(valid), outstanding_actions=len(analysis.metrics['outstanding_action_ids']))
    session.expire_all()
    return decide(session,conversation_id)


def decide(session, conversation_id):
    lock_event_writer(session)
    record, run = agent.runtime(session,conversation_id)
    analysis = saved_analysis(session,conversation_id)
    current_workflow=session.get(Workflow,run.workflow_id)
    action_plan.execute_local(session,analysis,allow_communication=current_workflow.code!='patient_intake' or run.status=='intake_complete')
    action_plan.mark_child_finished(session,record)
    session.flush()
    if analysis.decision:
        action_plan.refresh_metrics(session,analysis)
        session.commit()
        return {'decision':analysis.decision,'next_action':analysis.next_action}
    depth, parent = 1, record
    while parent.parent_conversation_id:
        depth += 1
        parent = session.get(ConversationRecord,parent.parent_conversation_id)
    remaining = {i['action_id'] for i in agent.state(session,run)['checklist'] if not i['ready']}
    queue=action_plan.call_queue(session,record)
    workflow=session.get(Workflow,run.workflow_id)
    may_route=workflow.code!='patient_intake' or run.status=='intake_complete'
    eligible=False
    if queue:
        task=queue[0]
        selected=session.scalar(select(Workflow).where(Workflow.code==task.workflow_code).order_by(Workflow.version.desc())) if task.workflow_code else None
        eligible=bool(selected and may_route and task.target!='practice')
        if eligible:
            analysis.next_action={'target':task.target,'objective':task.description,'workflow_code':task.workflow_code,
                                  'task_id':str(task.task_id),'action_code':task.action_code}
        else:
            task.status='blocked'; task.result={'reason':'intake_incomplete_or_invalid_workflow','simulated':True}
    elif analysis.next_action:
        eligible=bool(analysis.next_action.get('action_id') in remaining and run.status=='active')
    if eligible and depth < MAX_CALLS and not analysis.metrics['turn_limit_reached']:
        analysis.decision='continue'; record.status='follow_up_pending'
    else:
        unfinished=bool(queue) or run.status=='active' or analysis.metrics['turn_limit_reached'] or any(task.status in ('blocked','failed','pending') for task in action_plan.tasks(session,analysis))
        analysis.decision='needs_review' if unfinished else 'stop'
        record.status='needs_review' if unfinished else 'completed'
        if eligible and queue:
            for task in queue:
                task.status='blocked'; task.result={'reason':'call_or_turn_limit','simulated':True}
    action_plan.refresh_metrics(session,analysis)
    agent.publish(session,record,'conversation.finalized',status=record.status)
    log('analysis.decision', conversation_id=str(conversation_id), decision=analysis.decision,
        call_depth=depth, max_calls=MAX_CALLS, eligible=eligible, turn_limit_reached=analysis.metrics['turn_limit_reached'])
    result = {'decision':analysis.decision,'next_action':analysis.next_action}
    session.commit()
    return result


@router.post('/{conversation_id}/dispatch')
async def dispatch(conversation_id: UUID, session: Session = Depends(get_session)):
    log('follow_up.dispatch.requested', conversation_id=str(conversation_id))
    record, _ = agent.runtime(session,conversation_id)
    analysis = saved_analysis(session,conversation_id)
    if not analysis or not analysis.analyzed_at: raise HTTPException(409,'Analysis is not saved')
    if not analysis.decision:
        decide(session,conversation_id)
        analysis = saved_analysis(session,conversation_id)
    if analysis.decision != 'continue': return {'status':'stopped'}
    child = session.scalar(select(ConversationRecord).where(ConversationRecord.parent_conversation_id == record.id))
    if child: return {'status':'already_started','conversation_id':str(child.id)}
    return await simulator_request('POST','/continue', json={'conversation_id':str(record.source_conversation_id),'parent_conversation_id':str(record.id)})


def fail_record(session, conversation_id, reason):
    log('conversation.mark_failed', level=logging.WARNING, conversation_id=str(conversation_id), reason=reason)
    lock_event_writer(session)
    record, run = agent.runtime(session,conversation_id)
    if record.status in ('completed','continued','needs_review','failed'): return
    if record.parent_conversation_id:
        parent_analysis=saved_analysis(session,record.parent_conversation_id)
        task_id=(parent_analysis.next_action or {}).get('task_id') if parent_analysis else None
        task=session.get(ActionTask,UUID(task_id)) if task_id else None
        if task and task.status=='running':
            task.status='failed'; task.completed_at=datetime.now(timezone.utc)
            task.result={**task.result,'failure':reason}
            action_plan.refresh_metrics(session,parent_analysis)
    record.status = 'failed'
    record.end_time = record.end_time or datetime.now(timezone.utc)
    for turn in session.scalars(select(ConversationTranscript).where(ConversationTranscript.conversation_record_id == record.id, ConversationTranscript.end_time.is_(None))):
        turn.end_time = record.end_time
    if run is not None and run.status == 'active':
        run.status = 'cancelled' if reason == 'cancelled_by_user' else 'failed'
    analysis = saved_analysis(session,conversation_id)
    analysis.next_action = None
    analysis.decision = 'failed'
    analysis.metrics = {**(analysis.metrics or {}),'failure':reason}
    agent.publish(session,record,'conversation.finalized',status='failed')
    session.commit()


@router.post('/{conversation_id}/failed')
def failed(conversation_id: UUID, session: Session = Depends(get_session)):
    fail_record(session,conversation_id,'generation_or_dispatch_failed')
    return {'status':'failed'}
