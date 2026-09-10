from uuid import UUID
from fastapi import APIRouter, Depends, Query, Response, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from server.app.services.auth import require_auth, verify_origin
from server.core.database import get_session
from server.models.conversation import ConversationRecord, ConversationTranscript, ConversationEvent
from server.models.context import Patient, Provider, Prescription
from server.app.crud.conversations import lock_event_writer
from server.schemas.auth import AuthSession
from server.schemas.conversation import ConversationPage, ConversationSummary

router = APIRouter(tags=["conversations"])


@router.get("/conversations", response_model=ConversationPage)
def list_records(response: Response, limit: int = Query(50, ge=1, le=100),
                 offset: int = Query(0, ge=0), auth: AuthSession = Depends(require_auth),
                 session: Session = Depends(get_session)):
    scope = ConversationRecord.practice_id == auth.practice.practice_id
    total = session.scalar(select(func.count()).select_from(ConversationRecord).where(scope))
    rows = session.scalars(select(ConversationRecord).where(scope).order_by(
        ConversationRecord.start_time.desc(), ConversationRecord.id.desc(),
    ).offset(offset).limit(limit)).all()
    response.headers["Cache-Control"] = "no-store"
    return {"items": rows, "total": total}


@router.get('/conversations/{conversation_id}')
def details(conversation_id: UUID, response: Response, auth: AuthSession = Depends(require_auth),
            session: Session = Depends(get_session)):
    # Capture text and its event cursor atomically relative to the ingestion writer.
    lock_event_writer(session)
    record = session.scalar(select(ConversationRecord).where(
        ConversationRecord.id == conversation_id, ConversationRecord.practice_id == auth.practice.practice_id))
    if record is None:
        raise HTTPException(404, 'Conversation not found')
    turns = session.scalars(select(ConversationTranscript).where(
        ConversationTranscript.conversation_record_id == record.id).order_by(ConversationTranscript.turn_index)).all()
    cursor = session.scalar(select(func.max(ConversationEvent.id)).where(ConversationEvent.conversation_record_id == record.id)) or 0
    patient = session.get(Patient, record.patient_id) if record.patient_id else None
    provider = session.get(Provider, record.provider_id) if record.provider_id else None
    prescription = session.get(Prescription, record.prescription_id) if record.prescription_id else None
    response.headers['Cache-Control'] = 'no-store'
    return {'record': {**ConversationSummary.model_validate(record).model_dump(),
        'source_conversation_id': record.source_conversation_id, 'last_sequence': record.last_sequence,
        'practice_name': auth.practice.name,
        'patient_name': f'{patient.first_name} {patient.last_name}' if patient else None,
        'provider_name': f'{provider.first_name} {provider.last_name}' if provider else None,
        'medication_name': prescription.medication_name if prescription else None},
        'transcripts': [{'transcript_id': turn.transcript_id, 'speaker': turn.speaker,
            'transcript': turn.transcript, 'turn_index': turn.turn_index,
            'start_time': turn.start_time, 'end_time': turn.end_time} for turn in turns], 'cursor': cursor}


@router.get('/conversations/{conversation_id}/actions')
def action_details(conversation_id: UUID, auth: AuthSession = Depends(require_auth), session: Session = Depends(get_session)):
    from server.models.workflow import WorkflowRun
    from server.models.conversation import ConversationAnalysis
    from server.app.api.workflows import definition, view
    record = session.scalar(select(ConversationRecord).where(ConversationRecord.id == conversation_id,
        ConversationRecord.practice_id == auth.practice.practice_id))
    if record is None: raise HTTPException(404,'Conversation not found')
    run = session.scalar(select(WorkflowRun).where(WorkflowRun.conversation_id == record.id).order_by(WorkflowRun.created_at.desc()))
    analysis = session.scalar(select(ConversationAnalysis).where(ConversationAnalysis.conversation_record_id == record.id))
    child = session.scalar(select(ConversationRecord).where(ConversationRecord.parent_conversation_id == record.id))
    from server.app.services.action_plan import tasks
    planned=tasks(session,analysis) if analysis else []
    return {'tasks':[{'task_id':task.task_id,'kind':task.kind,'target':task.target,'description':task.description,
                     'workflow_code':task.workflow_code,'status':task.status,'result':task.result} for task in planned],
            'run':view(session,run) if run else None,
            'definition':definition(run.workflow_id,session,auth) if run else None,
            'analysis': {'summary':analysis.summary,'overall_sentiment':analysis.overall_sentiment,
                'reason_for_call':analysis.reason_for_call,'actions_needed':analysis.actions_needed,
                'metrics':analysis.metrics,'next_action':analysis.next_action,'decision':analysis.decision,
                'model':analysis.model,'analyzed_at':analysis.analyzed_at} if analysis else None,
            'status':record.status, 'parent_conversation_id':record.parent_conversation_id,
            'next_conversation_id':child.id if child else None}


@router.post('/conversations/{conversation_id}/cancel', dependencies=[Depends(verify_origin)])
async def cancel_conversation(conversation_id: UUID, auth: AuthSession = Depends(require_auth),
                              session: Session = Depends(get_session)):
    from server.app.api.agent import fail_record
    from server.app.api.simulations import simulator_request
    lock_event_writer(session)
    record = session.scalar(select(ConversationRecord).where(ConversationRecord.id == conversation_id,
        ConversationRecord.practice_id == auth.practice.practice_id))
    if record is None: raise HTTPException(404,'Conversation not found')
    if record.status not in ('live','failed'):
        raise HTTPException(409,'This conversation is no longer live')
    # Persist the stop before notifying the worker. Any late words/results are
    # rejected even if the simulator is temporarily unreachable.
    fail_record(session,conversation_id,'cancelled_by_user')
    session.commit()
    try:
        await simulator_request('POST','/cancel',json={'conversation_id':str(conversation_id)})
    except HTTPException:
        return {'status':'failed','message':'Conversation stopped. Simulator cancellation was not acknowledged; further transcript writes are blocked.'}
    return {'status':'failed','message':'Conversation cancelled. The partial transcript has been preserved.'}


@router.post('/conversations/{conversation_id}/analyze', dependencies=[Depends(verify_origin)])
async def rerun_analysis(conversation_id: UUID, auth: AuthSession = Depends(require_auth),
                         session: Session = Depends(get_session)):
    from starlette.concurrency import run_in_threadpool
    from server.app.api.agent import analyze, dispatch
    from server.schemas.agent import AnalyzeRequest
    record=session.scalar(select(ConversationRecord).where(ConversationRecord.id==conversation_id,
        ConversationRecord.practice_id==auth.practice.practice_id))
    if record is None: raise HTTPException(404,'Conversation not found')
    result=await run_in_threadpool(analyze,conversation_id,AnalyzeRequest(rerun=True),session)
    if result['decision']=='continue':
        try:
            result={**result,'dispatch':await dispatch(conversation_id,session)}
        except HTTPException as error:
            # The saved analysis and pending task survive an unavailable simulator.
            result={**result,'dispatch':{'status':'pending','detail':error.detail}}
    return result
