"""Evaluate checklist evidence without executing clinical or external actions."""
from datetime import datetime, timezone
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select
from server.models.workflow import ActionDefinition, RuleAction, WorkflowStep


def checklist(session, run):
    actions = session.scalars(select(ActionDefinition).join(RuleAction, RuleAction.action_id == ActionDefinition.action_id)
        .where(RuleAction.rule_id == run.current_rule_id).order_by(ActionDefinition.code)).all()
    latest = {row['action_id']: row for row in run.observations if row['rule_id'] == str(run.current_rule_id)}
    return [{'action_id': str(action.action_id), 'code': action.code, 'name': action.name,
             'instructions': action.instructions, 'actor': action.actor, 'timing': action.timing,
             'expected_result': action.result_fields,
             'observation': latest.get(str(action.action_id)),
             'ready': bool((row := latest.get(str(action.action_id))) and row['status'] == 'completed' and not row['missing_fields'] and not row['invalid_fields'])}
            for action in actions]


def record_result(session, run, action_id, status, result, evidence):
    if run.status != 'active':
        raise HTTPException(409, 'This run has reached its recorded outcome; start a new run for a new assessment.')
    membership = session.get(RuleAction, (run.current_rule_id, action_id))
    if membership is None:
        raise HTTPException(422, 'Action is not in the current rule checklist')
    action = session.get(ActionDefinition, action_id)
    missing, invalid = [], []
    for name, spec in action.result_fields.items():
        value = result.get(name)
        if value is None or value == '':
            if spec.get('required'): missing.append(name)
            continue
        valid_type = (isinstance(value, str) and bool(value.strip()) if spec['type'] == 'string' else
                      type(value) is bool if spec['type'] == 'boolean' else
                      isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value))
        if not valid_type or ('enum' in spec and value not in spec['enum']): invalid.append(name)
    invalid.extend(name for name in result if name not in action.result_fields)
    if action.code == 'collect_clinical_documentation' and result.get('status') == 'ready':
        if result.get('missing_documents'): invalid.append('missing_documents')
        if not result.get('received_documents'): invalid.append('received_documents')
    if not evidence.strip(): missing.append('evidence')
    run.observations = [*run.observations, {'rule_id': str(run.current_rule_id), 'action_id': str(action_id),
        'status': status, 'result': result, 'evidence': evidence,
        'missing_fields': missing, 'invalid_fields': sorted(set(invalid)), 'recorded_at': datetime.now(timezone.utc).isoformat()}]
    session.flush()


def advance(session, run):
    if run.status != 'active': raise HTTPException(409, 'Run is no longer active')
    items = checklist(session, run)
    if not items or not all(item['ready'] for item in items):
        raise HTTPException(409, 'Complete every required action and result field before advancing')
    step = session.get(WorkflowStep, (run.workflow_id, run.current_rule_id))
    values = {item['code']: item['observation']['result'] for item in items}
    matches = [branch for branch in step.branches if all(
        condition['field'] in values.get(condition['action'], {}) and
        values[condition['action']][condition['field']] == condition['equals'] for condition in branch['all'])]
    if len(matches) != 1: raise HTTPException(409, 'Results do not identify exactly one next step')
    branch = matches[0]
    if branch['next_rule'] and session.get(WorkflowStep,(run.workflow_id,UUID(branch['next_rule']))) is None:
        raise HTTPException(409, 'Next rule is not part of this workflow')
    run.completed_rules = [*run.completed_rules, str(run.current_rule_id)]
    if branch['next_rule']: run.current_rule_id = UUID(branch['next_rule'])
    else: run.status = branch['outcome']
    session.flush()
