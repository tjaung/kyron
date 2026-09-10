"""Trusted model tools: scoped record lookup and evidence-checked workflow progress."""
from datetime import datetime, timezone
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy import select, inspect
from fastapi.encoders import jsonable_encoder
from server.models.conversation import ConversationRecord, ConversationTranscript, ConversationAnalysis, ConversationEvent, Action
from server.models.context import Patient, Practice, Provider, Prescription
from server.models.health import PatientCondition, PatientAllergy, Encounter, PatientInsurance, Claim, PriorAuthorization
from server.models.simulation import SimulationConversation
from server.models.workflow import Workflow, WorkflowRun
from server.app.services.workflows import checklist, record_result, advance


def runtime(session, conversation_id):
    record = session.get(ConversationRecord, conversation_id)
    if record is None: raise HTTPException(404, 'Conversation not found')
    run = session.scalar(select(WorkflowRun).where(WorkflowRun.conversation_id == record.id).order_by(WorkflowRun.created_at.desc()))
    return record, run


def start_run(session, record):
    previous = None
    workflow_code = 'patient_intake'
    if record.parent_conversation_id:
        parent, previous = runtime(session, record.parent_conversation_id)
        analysis = session.scalar(select(ConversationAnalysis).where(ConversationAnalysis.conversation_record_id == parent.id))
        if (parent.source_conversation_id != record.source_conversation_id or parent.practice_id != record.practice_id
                or not analysis or analysis.decision != 'continue' or not previous):
            raise HTTPException(409, 'Parent is not eligible for continuation')
        workflow_code = analysis.next_action.get('workflow_code') or session.get(Workflow,previous.workflow_id).code
    workflow = session.scalar(select(Workflow).where(Workflow.code == workflow_code).order_by(Workflow.version.desc()))
    if workflow is None: raise HTTPException(409, 'Seed workflow definitions first')
    same = previous and previous.workflow_id == workflow.workflow_id and previous.status == 'active'
    run = WorkflowRun(conversation_id=record.id, practice_id=record.practice_id, workflow_id=workflow.workflow_id,
        current_rule_id=previous.current_rule_id if same else workflow.entry_rule_id,
        observations=list(previous.observations) if same else [],
        completed_rules=list(previous.completed_rules) if same else [], created_at=datetime.now(timezone.utc))
    session.add(run); session.flush()
    if previous and not same and workflow.code=='new_prescription':
        from server.core.workflow_seed import key
        verified=next((item for item in reversed(previous.observations)
            if item['action_id']==str(key('action','verify_identity')) and item['status']=='completed'
            and not item['missing_fields'] and not item['invalid_fields']
            and item['result'].get('verified') is True and item['result'].get('contact_permission') is True),None)
        if verified:
            run.observations=[{**verified,'rule_id':str(workflow.entry_rule_id)}]
            advance(session,run)
    return run


def row_data(row):
    return jsonable_encoder({c.key: getattr(row, c.key) for c in inspect(type(row)).columns}) if row else None


def context(session, record, run):
    source = session.get(SimulationConversation, record.source_conversation_id)
    scenario = {k:v for k,v in source.context.items() if k not in ('evaluation','expected_workflow')}
    prior_summary = None
    if record.parent_conversation_id:
        analysis = session.scalar(select(ConversationAnalysis).where(ConversationAnalysis.conversation_record_id == record.parent_conversation_id))
        scenario = {**scenario, 'counterpart': analysis.next_action['target'], 'objective': analysis.next_action['objective']}
        prior_summary = analysis.summary
    facts = {'patient': row_data(session.get(Patient, record.patient_id)) if record.patient_id else None,
             'practice': row_data(session.get(Practice, record.practice_id)),
             'provider': row_data(session.get(Provider, record.provider_id)) if record.provider_id else None,
             'prescription': row_data(session.get(Prescription, record.prescription_id)) if record.prescription_id else None}
    # These read-only tools always derive scope from the persisted conversation.
    for name, model, predicate in [
        ('conditions',PatientCondition,PatientCondition.patient_id == record.patient_id),
        ('allergies',PatientAllergy,PatientAllergy.patient_id == record.patient_id),
        ('encounters',Encounter,Encounter.patient_practice_id == record.patient_practice_id),
        ('coverage',PatientInsurance,PatientInsurance.patient_id == record.patient_id),
        ('claims',Claim,(Claim.patient_practice_id == record.patient_practice_id) & (Claim.claim_type == 'pharmacy')),
        ('authorizations',PriorAuthorization,PriorAuthorization.prescription_id == record.prescription_id)]:
        facts[name] = [row_data(row) for row in session.scalars(select(model).where(predicate)).all()]
    return {'scenario':scenario, 'facts':facts, 'prior_summary':prior_summary, 'workflow': state(session,run)}


def state(session, run):
    return jsonable_encoder({'run_id':run.run_id,'workflow_id':run.workflow_id,
        'workflow_code':session.get(Workflow,run.workflow_id).code,'status':run.status,
        'current_rule_id':run.current_rule_id,'completed_rules':run.completed_rules,
        'observations':run.observations,'checklist':checklist(session,run) if run.status == 'active' else []})


def observe(session, record, run, observations, after_call=False):
    if record.status != 'live' and not (after_call and record.status in ('ended','processing')): raise HTTPException(409, 'Conversation is not live')
    turns = session.scalars(select(ConversationTranscript).where(ConversationTranscript.conversation_record_id == record.id)).all()
    corpus = '\n'.join(turn.transcript for turn in turns)
    for item in observations:
        if not item.evidence.strip() or item.evidence not in corpus:
            raise HTTPException(422, 'Evidence must quote an actual turn in this conversation')
        from server.core.workflow_seed import key
        if (session.get(Workflow,run.workflow_id).code=='patient_intake'
                and item.action_id==key('action','verify_identity') and item.status=='completed'):
            from server.app.services.intake_evidence import permission, identity_matches
            known_permission=permission(turns)
            if known_permission is None or item.result.get('contact_permission') is not known_permission:
                raise HTTPException(422,'Permission must match an explicit caller response; missing permission is not refusal')
            patient=session.get(Patient,record.patient_id) if record.patient_id else None
            if item.result.get('verified') is True and not identity_matches(patient,turns):
                raise HTTPException(422,'The caller must confirm their recorded name and birth date')
        record_result(session, run, item.action_id, item.status, item.result, item.evidence)
        run.observations = [*run.observations[:-1], {**run.observations[-1], 'conversation_id':str(record.id)}]
        observation = run.observations[-1]
        analysis = session.scalar(select(ConversationAnalysis).where(ConversationAnalysis.conversation_record_id == record.id))
        from server.models.workflow import ActionDefinition
        definition = session.get(ActionDefinition,item.action_id)
        turn = next((turn for turn in turns if item.evidence in turn.transcript and turn.action is None),None)
        execution = Action(action_id=uuid4(), action_definition_id=item.action_id, analysis_id=analysis.analysis_id,
            transcript_id=turn.transcript_id if turn else None, action=definition.code, reason=item.evidence,
            is_completed=item.status=='completed' and not observation['missing_fields'] and not observation['invalid_fields'])
        session.add(execution)
        if turn: turn.action = execution.action_id
        session.flush()
    if observations and all(item['ready'] for item in checklist(session,run)):
        advance(session,run)
    return state(session,run)


def publish(session, record, event_type, **fields):
    record.last_sequence += 1
    session.add(ConversationEvent(conversation_record_id=record.id, sequence=record.last_sequence,
        data={'type':event_type,'conversation_id':str(record.id),'sequence':record.last_sequence,
              'occurred_at':datetime.now(timezone.utc).isoformat(), **fields}))
