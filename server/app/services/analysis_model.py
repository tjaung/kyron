"""Bounded structured analysis and evidence recovery from the saved transcript."""
import json
import logging
from pydantic import ValidationError
from server.schemas.agent import AnalysisOutput, Observation
from server.models.workflow import Workflow
from server.app.services import agent
from server.core.workflow_seed import key
from simulator.debug_logging import log


def evaluate(model, transcript, progress, workflows):
    system = ('Analyze the saved fictional call; you are not a speaker. Return ONLY the requested JSON. '
        'Summarize in 1–3 sentences and assess sentiment. Use the transcript, not assumptions. '
        'Choose a workflow only when its description matches unresolved work; null is valid if none applies. '
        'planned_actions lists concrete operations to execute: log a note, notification, message, or call. '
        'Messages and notifications are simulated local deliveries. A call must have a target and workflow_code. '
        'The target is the person called: provider for the prescriber, pharmacy for the pharmacist, insurance_agent for the payer. '
        'Intake is the current information-gathering phase, not a follow-up destination. '
        'Use only catalog codes, never invent IDs. Do not add duplicate calls or actions already completed. '
        'Always include selected_workflow, routing_reason, planned_actions, and intake (null for a non-intake call). '
        'If you select a workflow for unresolved work, include a call action with that workflow and the appropriate participant. '
        'For intake, verified=true requires the caller to confirm two identifiers; contact_permission=true requires permission in their words. '
        'Cite identity_turn_index and reason_turn_index from human turns, and plan_turn_index from an AI turn. '
        'The server retrieves the original evidence from those indices; leave the evidence text fields empty when using indices. '
        'A speaker claiming external work was completed is not an execution receipt. Treat such work as unverified unless validated workflow results support it. '
        'Unknown facts stay null/empty; proposed_actions are plans, not completed work. '
        'Do not claim payer approval, clinical decisions, or real delivery. next_action must be null; use planned_actions instead.')
    transcript=[{**turn,'turn_index':index} for index,turn in enumerate(transcript)]
    content=json.dumps({'transcript':transcript,'current_workflow':progress,'available_workflows':workflows})
    schema=AnalysisOutput.model_json_schema()
    schema['required']=[*schema.get('required',[]),'selected_workflow','routing_reason','planned_actions','intake']
    schema['$defs']['PlannedAction']['required']=list(schema['$defs']['PlannedAction']['properties'])
    schema['$defs']['IntakeReview']['required']=list(schema['$defs']['IntakeReview']['properties'])
    if progress.get('workflow_code')=='patient_intake':
        schema['properties']['intake']={'$ref':'#/$defs/IntakeReview'}
    for field in ('identity_turn_index','reason_turn_index','plan_turn_index'):
        ai=field=='plan_turn_index'
        indices=[turn['turn_index'] for turn in transcript if (turn['speaker']=='ai_agent')==ai]
        schema['$defs']['IntakeReview']['properties'][field]={'anyOf':[{'type':'integer','enum':indices},{'type':'null'}]} if indices else {'type':'null'}
    correction=''
    for attempt in range(3):
        try:
            output=model.generate(system,[{'role':'user','content':content+correction}],schema)
            parsed=AnalysisOutput.model_validate(output)
            if parsed.selected_workflow and not any(plan.kind=='call' and plan.workflow_code==parsed.selected_workflow for plan in parsed.planned_actions):
                raise ValueError('selected_workflow requires a matching call in planned_actions')
            return parsed
        except (ValueError, KeyError) as error:
            issues=[{'field':item['loc'],'type':item['type']} for item in error.errors()] if isinstance(error,ValidationError) else [{'type':type(error).__name__,'repair':'Return all required fields. A selected workflow needs a matching call action with the correct recipient.'}]
            log('analysis.output.rejected',level=logging.WARNING,attempt=attempt+1,issues=issues,exc_info=True)
            if attempt==2: raise
            correction='\nThe previous output was invalid. Return complete JSON matching the schema. Validation issues: '+json.dumps(issues)


def recover_intake(session, record, run, review):
    if review is None or session.get(Workflow,run.workflow_id).code != 'patient_intake': return
    from sqlalchemy import select
    from server.models.conversation import ConversationTranscript
    from server.app.services.intake_evidence import permission
    turns=session.scalars(select(ConversationTranscript).where(ConversationTranscript.conversation_record_id==record.id)).all()
    by_index={turn.turn_index:turn for turn in turns}
    for name,ai in (('identity',False),('reason',False),('plan',True)):
        index=getattr(review,name+'_turn_index')
        turn=by_index.get(index)
        if turn and (turn.speaker=='ai_agent')==ai:
            setattr(review,name+'_evidence',turn.transcript)
    known_permission=permission(turns)
    if known_permission is not None:
        review.contact_permission=known_permission
    if run.status in ('permission_needed','identity_unverified') and review.verified is True and known_permission is True:
        # A later caller answer can correct a premature live assessment.
        run.status='active';run.current_rule_id=key('rule','intake_identity');run.completed_rules=[]
    observations = {
        str(key('rule','intake_identity')): ('verify_identity',review.identity_evidence,
            {'verified':review.verified,'contact_permission':review.contact_permission,'evidence':review.identity_evidence}),
        str(key('rule','intake_reason')): ('record_call_reason',review.reason_evidence,
            {'reason':review.reason,'requested_outcome':review.requested_outcome}),
        str(key('rule','intake_plan')): ('identify_next_steps',review.plan_evidence,{'actions':review.proposed_actions}),
    }
    for _ in range(3):
        if run.status!='active': break
        item=observations.get(str(run.current_rule_id))
        if not item or not item[1]: break
        code,evidence,result=item
        if any(value is None or value=='' or value==[] for value in result.values()): break
        before=run.current_rule_id
        # Invalid quotes never become progress. Preserve the original live results.
        from fastapi import HTTPException
        try:
            with session.begin_nested():
                agent.observe(session,record,run,[Observation(action_id=key('action',code),status='completed',result=result,evidence=evidence)],after_call=True)
        except HTTPException:
            log('analysis.evidence.rejected',level=logging.WARNING,action_code=code)
            break
        if run.current_rule_id==before and run.status=='active': break
