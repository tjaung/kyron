"""Durable simulated action execution; no external messages or clinical mutations."""
from datetime import datetime, timezone
import hashlib
from uuid import UUID
from sqlalchemy import select
from server.models.conversation import ActionTask, ConversationAnalysis, ConversationRecord
from server.models.workflow import Workflow
from simulator.debug_logging import log


def tasks(session, analysis):
    return session.scalars(select(ActionTask).where(ActionTask.analysis_id == analysis.analysis_id)
                           .order_by(ActionTask.created_at, ActionTask.task_id)).all()


def save(session, analysis, plans):
    existing = {task.dedupe_key:task for task in tasks(session,analysis)}
    selected = set()
    for plan in plans:
        # The same logical operation remains the same task on analysis retry.
        key = hashlib.sha256('|'.join([plan.kind,plan.target,plan.workflow_code or '',plan.action_code or '']).encode()).hexdigest()
        selected.add(key)
        task = existing.get(key)
        if task is None:
            task = ActionTask(analysis_id=analysis.analysis_id,dedupe_key=key,kind=plan.kind,target=plan.target,
                description=plan.description,workflow_code=plan.workflow_code,action_code=plan.action_code,
                created_at=datetime.now(timezone.utc),status='pending',result={})
            session.add(task); existing[key]=task
        elif task.status not in ('completed','running') and not (task.kind=='call' and task.result.get('conversation_id')):
            task.description=plan.description; task.status='pending'; task.result={}
    for key,task in existing.items():
        if key not in selected and task.status in ('pending','blocked','failed'):
            task.status='superseded'
    session.flush()


def execute_local(session, analysis, allow_communication=True):
    for task in tasks(session,analysis):
        if task.status != 'pending' or task.kind == 'call': continue
        if task.kind in ('message','notification') and not allow_communication:
            task.status='blocked'; task.result={'simulated':True,'reason':'intake_incomplete'}
            continue
        # A receipt is a simulated delivery, never a real email/SMS or payer result.
        task.result={'simulated':True,'operation':task.kind,'recipient':task.target,
                     'receipt':f'sim-{task.task_id}','content':task.description}
        task.status='completed'; task.completed_at=datetime.now(timezone.utc)
        log('action.executed',task_id=str(task.task_id),kind=task.kind,simulated=True)
    session.flush()


def call_queue(session, record):
    lineage=[]; current=record
    while current:
        lineage.append(current.id)
        current=session.get(ConversationRecord,current.parent_conversation_id) if current.parent_conversation_id else None
    return session.scalars(select(ActionTask).join(ConversationAnalysis,ActionTask.analysis_id==ConversationAnalysis.analysis_id)
        .where(ConversationAnalysis.conversation_record_id.in_(lineage),ActionTask.kind=='call',ActionTask.status=='pending')
        .order_by(ActionTask.created_at,ActionTask.task_id)).all()


def mark_child_finished(session, record):
    if not record.parent_conversation_id: return
    parent_analysis=session.scalar(select(ConversationAnalysis).where(ConversationAnalysis.conversation_record_id==record.parent_conversation_id))
    task_id=(parent_analysis.next_action or {}).get('task_id') if parent_analysis else None
    task=session.get(ActionTask,UUID(task_id)) if task_id else None
    if task and task.status in ('running','failed'):
        task.status='completed'; task.completed_at=datetime.now(timezone.utc)
        task.result={**{key:value for key,value in task.result.items() if key!='failure'},'analysis_saved':True}
        refresh_metrics(session,parent_analysis)


def refresh_metrics(session, analysis):
    session.flush()
    rows=[task for task in tasks(session,analysis) if task.status!='superseded']
    analysis.metrics={**(analysis.metrics or {}),'actions_total':len(rows),
                      'actions_completed':sum(task.status=='completed' for task in rows),
                      'actions_pending':sum(task.status in ('pending','running') for task in rows),
                      'actions_blocked_or_failed':sum(task.status in ('blocked','failed') for task in rows)}
