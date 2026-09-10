"""Administrative new-prescription workflow; payer requirements are supplied evidence, not invented policy."""
from uuid import NAMESPACE_URL, uuid5
from server.models.workflow import ActionDefinition, Rule, RuleAction, Workflow, WorkflowStep


def key(kind, code):
    return uuid5(NAMESPACE_URL, f'kyron/workflow/v1/{kind}/{code}')


def field(kind='string', values=None):
    value = {'type': kind, 'required': True}
    if values: value['enum'] = values
    return value


# Expected results describe what must be recorded, including explicit negative outcomes.
ACTIONS = {
 'call_insurance': ('Contact payer for prescription status', 'Contact the appropriate payer channel and record the response reference. A call request alone is not a completed authorization.', 'ai_agent', 'after_call', {'contacted':field('boolean'), 'reference':field()}),
 'call_patient': ('Return patient call', 'Verify identity before sharing the outcome and document successful or unsuccessful contact.', 'ai_agent', 'after_call', {'contacted':field('boolean'), 'reference':field()}),
 'verify_identity': ('Verify patient and contact permission', 'Confirm two identifiers, practice linkage, and permission to communicate. Do not disclose records before confirmation.', 'ai_agent', 'during_call', {'verified':field('boolean'), 'contact_permission':field('boolean'), 'evidence':field()}),
 'assess_urgency': ('Check whether clinician help is needed', 'Ask about reported urgent symptoms or risk from running out. Escalate to the practice clinician under local policy; do not provide independent treatment advice.', 'ai_agent', 'during_call', {'urgent':field('boolean'), 'patient_report':field()}),
 'review_prescription_record': ('Verify a prescriber-issued prescription', 'Match patient, prescriber, drug, strength, directions, quantity, refills, and destination pharmacy. The AI cannot issue a prescription.', 'ai_agent', 'during_call', {'status':field(values=['valid','missing','expired','unclear']), 'evidence':field()}),
 'request_prescriber_renewal': ('Request prescriber review or new order', 'Send the request and clinical question to the authorized prescriber. Record acknowledgement; do not claim a new order exists until received.', 'ai_agent', 'after_call', {'request_reference':field(), 'recipient':field(), 'follow_up_at':field()}),
 'verify_coverage': ('Verify active pharmacy coverage', 'Confirm current member details and pharmacy benefit coverage with payer evidence.', 'ai_agent', 'during_call', {'status':field(values=['active','inactive','unknown']), 'payer_reference':field()}),
 'request_updated_coverage': ('Request corrected insurance details', 'Ask for the new insurance card through the approved channel and assign follow-up.', 'ai_agent', 'after_call', {'request_reference':field(), 'follow_up_at':field()}),
 'check_pharmacy_claim': ('Check pharmacy claim processing', 'Ask the pharmacy to process the valid order and report paid, rejected, or pending status plus the exact rejection reason. PA approval does not guarantee a paid claim.', 'ai_agent', 'during_call', {'status':field(values=['paid','rejected','pending']), 'reason':field(values=['none','prior_authorization','non_formulary','other']), 'pharmacy_reference':field()}),
 'check_prior_authorization_requirements': ('Check payer PA requirements and existing case', 'Obtain drug-specific documentation requirements and any existing PA decision/reference. Do not submit duplicate requests or guess payer rules.', 'ai_agent', 'during_call', {'status':field(values=['not_submitted','pending','approved','denied','not_required']), 'payer_reference':field(), 'requirements':field('list')}),
 'collect_clinical_documentation': ('Collect required supporting records', 'Obtain the payer-requested diagnosis, visit notes, and prior treatment information from the prescriber. Missing data stays missing; never fabricate it.', 'ai_agent', 'after_call', {'status':field(values=['ready','missing']), 'received_documents':field('list'), 'missing_documents':field('list')}),
 'confirm_prescriber_support': ('Confirm prescriber authorization and rationale', 'Obtain prescriber review and any required supporting statement/signature; the prescriber determines medical necessity.', 'prescriber', 'after_call', {'status':field(values=['confirmed','missing']), 'evidence':field()}),
 'submit_prior_authorization': ('Submit complete PA request', 'Submit only after documentation and prescriber support are complete. Store receipt, payer reference, submission time, and payer-provided follow-up deadline.', 'ai_agent', 'after_call', {'submitted':field('boolean'), 'payer_reference':field(), 'submitted_at':field(), 'follow_up_at':field()}),
 'document_insurance_status': ('Record PA decision', 'Record the actual payer decision, reason, reference, and approval dates when supplied. Pending is not approval.', 'ai_agent', 'during_call', {'status':field(values=['approved','denied','pending']), 'payer_reference':field(), 'decision_reason':field()}),
 'route_denial_to_prescriber': ('Route denial or formulary issue for clinical review', 'Capture denial reason and payer appeal/exception instructions. Let the prescriber decide whether to request an exception, appeal, or issue a different prescription.', 'ai_agent', 'after_call', {'denial_reference':field(), 'review_request_reference':field(), 'follow_up_at':field()}),
 'request_visit_note': ('Request missing documentation', 'Identify the exact missing records, assign an owner, and record when to follow up. Keep the case waiting.', 'ai_agent', 'after_call', {'missing_documents':field('list'), 'owner':field(), 'follow_up_at':field()}),
 'notify_pharmacy': ('Send authorization result to pharmacy', 'Provide the PA reference and ask the pharmacy to rerun the claim; do not promise availability or payment.', 'ai_agent', 'after_call', {'notification_reference':field(), 'payer_reference':field()}),
 'confirm_fill_ready': ('Confirm prescription is ready', 'Ask the pharmacy for actual dispensing readiness, stock/delivery status, and patient cost. A paid claim alone is insufficient.', 'ai_agent', 'during_call', {'status':field(values=['ready','delayed']), 'pharmacy_reference':field(), 'patient_cost':field(), 'pickup_or_delivery':field()}),
 'record_patient_followup': ('Explain outcome and next step to patient', 'Confirm identity before disclosure. Explain the actual outcome, outstanding work, responsible party, and follow-up plan. Record delivery or unsuccessful contact.', 'ai_agent', 'during_call', {'status':field(values=['communicated','unable_to_reach']), 'summary':field(), 'next_step':field()}),
 'schedule_followup': ('Assign follow-up', 'Record unresolved issue, owner, next contact time, and escalation instructions. Do not label the prescription filled.', 'ai_agent', 'after_call', {'owner':field(), 'follow_up_at':field(), 'reason':field()}),
 'escalate_to_clinician': ('Hand off clinical concern', 'Transfer urgent/uncertain clinical issues using the practice protocol and document acknowledgement.', 'ai_agent', 'during_call', {'recipient':field(), 'handoff_reference':field()}),
}

# Branch predicates use action-code.field equality, never executable expressions.
def when(action, field_name, value, target=None, outcome=None):
    return {'all': [{'action': action, 'field': field_name, 'equals': value}], 'next_rule': target, 'outcome': outcome}


def always(target=None, outcome=None):
    return {'all': [], 'next_rule': target, 'outcome': outcome}


RULES = {
 'identity': (['verify_identity'], [
     {'all':[{'action':'verify_identity','field':'verified','equals':True},{'action':'verify_identity','field':'contact_permission','equals':True}], 'next_rule':'urgency', 'outcome':None},
     when('verify_identity','verified',False,outcome='identity_unverified'),
     {'all':[{'action':'verify_identity','field':'verified','equals':True},{'action':'verify_identity','field':'contact_permission','equals':False}], 'next_rule':None,'outcome':'permission_needed'}]),
 'urgency': (['assess_urgency'], [when('assess_urgency','urgent',True,'clinical_handoff'),when('assess_urgency','urgent',False,'prescription')]),
 'clinical_handoff': (['escalate_to_clinician'], [always(outcome='clinician_handoff')]),
 'prescription': (['review_prescription_record'], [when('review_prescription_record','status',s,'coverage' if s=='valid' else 'prescriber_order') for s in ('valid','missing','expired','unclear')]),
 'prescriber_order': (['request_prescriber_renewal','schedule_followup'], [always(outcome='waiting_for_prescriber')]),
 'coverage': (['verify_coverage'], [when('verify_coverage','status',s,'claim' if s=='active' else 'coverage_update') for s in ('active','inactive','unknown')]),
 'coverage_update': (['request_updated_coverage','schedule_followup'], [always(outcome='waiting_for_coverage')]),
 'claim': (['check_pharmacy_claim'], [when('check_pharmacy_claim','status','paid','fill'),when('check_pharmacy_claim','status','pending','followup'),
     *[{'all':[{'action':'check_pharmacy_claim','field':'status','equals':'rejected'},{'action':'check_pharmacy_claim','field':'reason','equals':reason}], 'next_rule':target, 'outcome':None} for reason,target in [('prior_authorization','pa_requirements'),('non_formulary','denial'),('other','followup'),('none','followup')]]]),
 'pa_requirements': (['check_prior_authorization_requirements'], [when('check_prior_authorization_requirements','status',s,target) for s,target in [('not_submitted','documentation'),('pending','followup'),('approved','pharmacy_notification'),('denied','denial'),('not_required','followup')]]),
 'documentation': (['collect_clinical_documentation','confirm_prescriber_support'], [
     {'all':[{'action':'collect_clinical_documentation','field':'status','equals':'ready'},{'action':'confirm_prescriber_support','field':'status','equals':'confirmed'}], 'next_rule':'submit_pa','outcome':None},
     when('collect_clinical_documentation','status','missing','missing_documents'),
     {'all':[{'action':'collect_clinical_documentation','field':'status','equals':'ready'},{'action':'confirm_prescriber_support','field':'status','equals':'missing'}], 'next_rule':'missing_documents','outcome':None}]),
 'missing_documents': (['request_visit_note','schedule_followup'], [always(outcome='waiting_for_documents')]),
 'submit_pa': (['submit_prior_authorization'], [when('submit_prior_authorization','submitted',True,'decision'),when('submit_prior_authorization','submitted',False,'followup')]),
 'decision': (['document_insurance_status'], [when('document_insurance_status','status',s,target) for s,target in [('approved','pharmacy_notification'),('denied','denial'),('pending','followup')]]),
 'pharmacy_notification': (['notify_pharmacy'], [always('claim_recheck')]),
 'claim_recheck': (['check_pharmacy_claim'], [when('check_pharmacy_claim','status',s,'fill' if s=='paid' else 'followup') for s in ('paid','rejected','pending')]),
 'denial': (['route_denial_to_prescriber','schedule_followup'], [always(outcome='waiting_for_prescriber_review')]),
 'fill': (['confirm_fill_ready'], [when('confirm_fill_ready','status','ready','patient_notification'),when('confirm_fill_ready','status','delayed','followup')]),
 'patient_notification': (['record_patient_followup'], [when('record_patient_followup','status','communicated',outcome='ready_and_patient_notified'),when('record_patient_followup','status','unable_to_reach','followup')]),
 'followup': (['schedule_followup','record_patient_followup'], [always(outcome='waiting_for_followup')]),
}


def seed_workflow(session):
    for code, (name, instructions, actor, timing, fields) in ACTIONS.items():
        if session.get(ActionDefinition, key('action', code)) is None:
            session.add(ActionDefinition(action_id=key('action', code), code=code, version=1, name=name,
                instructions=instructions, actor=actor, timing=timing, result_fields=fields))
    for code in RULES:
        if session.get(Rule, key('rule', code)) is None:
            session.add(Rule(rule_id=key('rule', code), code=code, version=1, name=code.replace('_',' ').title(),
                description='Complete every checklist action with required results before choosing a branch. Actions within this checklist may occur in any order.'))
    session.flush()
    workflow_id = key('workflow','new_prescription')
    if session.get(Workflow, workflow_id) is None:
        session.add(Workflow(workflow_id=workflow_id, code='new_prescription', version=1, name='New prescription fulfillment',
            description='Administrative workflow from patient inquiry to pharmacy readiness. Waiting and clinician handoff are explicit outcomes; this workflow does not prescribe or change treatment.', entry_rule_id=key('rule','identity')))
    session.flush()
    for code, (actions, branches) in RULES.items():
        for action in actions:
            if session.get(RuleAction, (key('rule',code),key('action',action))) is None:
                session.add(RuleAction(rule_id=key('rule',code),action_id=key('action',action)))
        if session.get(WorkflowStep,(workflow_id,key('rule',code))) is None:
            session.add(WorkflowStep(workflow_id=workflow_id,rule_id=key('rule',code),branches=[
                {**branch,'next_rule':str(key('rule',branch['next_rule'])) if branch['next_rule'] else None} for branch in branches]))
    session.flush()


def seed_intake(session):
    definitions = {
        'record_call_reason': ('Record reason for contact', 'Ask what the caller needs and record their desired outcome.', {'reason':field(), 'requested_outcome':field()}),
        'identify_next_steps': ('Identify proposed next actions', 'Record the proposed next steps discussed with the caller. These are a plan, not completed external actions.', {'actions':field('list')}),
    }
    for code, (name, instructions, fields) in definitions.items():
        if session.get(ActionDefinition,key('action',code)) is None:
            session.add(ActionDefinition(action_id=key('action',code),code=code,version=1,name=name,
                instructions=instructions,actor='ai_agent',timing='during_or_after_call',result_fields=fields))
    rules = {
        'intake_identity': (['verify_identity'], [
            {'all':[{'action':'verify_identity','field':'verified','equals':True},{'action':'verify_identity','field':'contact_permission','equals':True}], 'next_rule':'intake_reason','outcome':None},
            when('verify_identity','verified',False,outcome='identity_unverified'),
            {'all':[{'action':'verify_identity','field':'verified','equals':True},{'action':'verify_identity','field':'contact_permission','equals':False}], 'next_rule':None,'outcome':'permission_needed'}]),
        'intake_reason': (['record_call_reason'], [always('intake_plan')]),
        'intake_plan': (['identify_next_steps'], [always(outcome='intake_complete')]),
    }
    for code in rules:
        if session.get(Rule,key('rule',code)) is None:
            session.add(Rule(rule_id=key('rule',code),code=code,version=1,name=code.replace('_',' ').title(),
                description='Gather patient intake information from recorded conversation evidence.'))
    session.flush()
    workflow_id=key('workflow','patient_intake')
    if session.get(Workflow,workflow_id) is None:
        session.add(Workflow(workflow_id=workflow_id,code='patient_intake',version=1,name='Patient call intake',
            description='Verify identity, understand the request, and identify proposed next steps before routing.',entry_rule_id=key('rule','intake_identity')))
    session.flush()
    for code,(actions,branches) in rules.items():
        for action in actions:
            if session.get(RuleAction,(key('rule',code),key('action',action))) is None:
                session.add(RuleAction(rule_id=key('rule',code),action_id=key('action',action)))
        if session.get(WorkflowStep,(workflow_id,key('rule',code))) is None:
            session.add(WorkflowStep(workflow_id=workflow_id,rule_id=key('rule',code),branches=[
                {**branch,'next_rule':str(key('rule',branch['next_rule'])) if branch['next_rule'] else None} for branch in branches]))
    session.flush()
