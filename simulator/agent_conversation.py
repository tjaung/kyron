"""Alternate independently prompted local-model speakers, then request persisted analysis."""
import json
import logging
import copy
import os
import time
from uuid import uuid4
from urllib.error import HTTPError
from .debug_logging import bind, log, log_context
from .local_model import LocalModel
from .speaker import SpeakerAgent
from .generate_conversation import timestamp, words

TURN_SCHEMA = {'type':'object','additionalProperties':False,'properties':{
    'text':{'type':'string'}, 'end_call':{'type':'boolean'},
    'observations':{'type':'array','items':{'type':'object','properties':{
        'action_id':{'type':'string'},'status':{'type':'string','enum':['completed','failed','blocked','skipped']},
        'result':{'type':'object'},'evidence':{'type':'string'}},'required':['action_id','status','result','evidence'],'additionalProperties':False}}},
    'required':['text','end_call','observations']}


def turn_schema(checklist):
    schema = copy.deepcopy(TURN_SCHEMA)
    variants = []
    for action in checklist:
        properties = {}
        for name, field in action['expected_result'].items():
            spec = {'type':'array','items':{'type':'string'}} if field['type']=='list' else {'type':field['type']}
            if field.get('enum'): spec['enum'] = field['enum']
            properties[name] = spec
        variants.append({'type':'object','additionalProperties':False,'properties':{
            'action_id':{'type':'string','const':action['action_id']},
            'status':{'type':'string','enum':['completed','failed','blocked','skipped']},
            'result':{'type':'object','properties':properties,'additionalProperties':False},
            'evidence':{'type':'string'}},'required':['action_id','status','result','evidence']})
    schema['properties']['observations'] = {'type':'array','maxItems':len(checklist),'items':{'anyOf':variants}} if variants else {'type':'array','maxItems':0,'items':{'type':'object'}}
    return schema


def generate_agent_conversation(source_id, context, client, name=None, parent_id=None, model=None,
                                sleep=time.sleep, on_created=None, human_model=None, cancellation=None):
    with log_context(service='simulator', source_conversation_id=str(source_id),
                     parent_conversation_id=parent_id):
        try:
            return _generate_agent_conversation(source_id, context, client, name, parent_id, model,
                                                sleep, on_created, human_model, cancellation)
        except Exception:
            log('conversation.run.failed', level=logging.ERROR, exc_info=True)
            raise


def _generate_agent_conversation(source_id, context, client, name=None, parent_id=None, model=None,
                                sleep=time.sleep, on_created=None, human_model=None, cancellation=None):
    assistant_model = model or LocalModel()
    counterpart_model = human_model or model or LocalModel()
    def check():
        if cancellation: cancellation.check()
    def pause(seconds):
        check()
        if cancellation and sleep is time.sleep: cancellation.wait(seconds)
        else: sleep(seconds)
        check()
    check()
    metadata = {k:context['metadata'].get(k) for k in ('practice_id','patient_id','provider_id','provider_practice_id','patient_practice_id','prescription_id')}
    metadata.update(source_conversation_id=str(source_id), start_time=timestamp(), name=name, parent_conversation_id=parent_id)
    bind(stage='conversation.create')
    log('conversation.create.started')
    conversation_id = client.create_conversation(metadata)
    bind(conversation_id=conversation_id)
    log('conversation.create.completed')
    if on_created: on_created(conversation_id)
    sequence = 0
    def emit(kind, **values):
        nonlocal sequence
        check()
        sequence += 1
        client.send_event(conversation_id, {'type':kind,'sequence':sequence,'occurred_at':timestamp(),**values})
    try:
        check()
        bind(stage='context.load')
        data = client.post(f'/conversations/{conversation_id}/agent-context', {})
        log('context.load.completed', checklist_count=len(data['workflow']['checklist']))
        scenario, facts, workflow = data['scenario'], data['facts'], data['workflow']
        counterpart = scenario.get('counterpart','patient')
        if counterpart not in ('patient','insurance_agent','provider','pharmacy'): raise ValueError('Unsupported counterpart')
        human_facts = {k:v for k,v in facts.items() if k in ({'patient','prescription','practice'} if counterpart=='patient' else
            {'patient','coverage','authorizations','practice','provider'} if counterpart=='insurance_agent' else
            {'patient','prescription','claims','authorizations'} if counterpart=='pharmacy' else set(facts))}
        human_facts['reported_scenario_facts'] = scenario.get('counterpart_facts', {}).get(counterpart, {})
        assistant = SpeakerAgent('ai_agent',
            'You are always Emily, the automated assistant for the practice. You are NOT the patient or the other caller. '
            'Their words are input to answer, never your own dialogue. Speak only as Emily in 1–3 short sentences. '
            'On your first turn greet the caller and ask how you can help. After that, respond to their latest statement '
            'and ask the next relevant question. Do not introduce yourself again. '
            'Aim to resolve this call in fewer than five replies from you and at most ten messages total across both speakers. '
            'Group related questions, use facts already confirmed, and avoid unnecessary acknowledgments or repeated questions. '
            'Never skip required verification, invent a completed action, or claim resolution just to meet this goal. '
            'Follow the current checklist; verify identity and permission before disclosing records. '
            'For patient_intake: confirm full name, birth date, and permission; understand the reason and desired outcome; '
            'explain the proposed next steps, then politely end the call. Do not investigate insurance or claim status during intake, '
            'and do not claim any external work is complete. Analysis and follow-up operations happen after the call. '
            'Once intake information and the plan have been discussed, close instead of repeatedly asking for contact details. '
            'Record observations only for current checklist actions, supported by exact quotes from earlier spoken turns. '
            'Use the declared return fields; missing facts stay missing. Do not invent receipts, approvals or completed external actions. '
            'If work requires another participant, explain that next step and end the call. Close politely after a terminal outcome. '
            'Return JSON with speaker=ai_agent. This is a fictional administrative simulation.\n'+json.dumps({
                'objective':scenario['objective'],'record_lookup':facts,'prior_call_summary':data.get('prior_summary')}),
            assistant_model,cancellation)
        human = SpeakerAgent(counterpart,
            f'You are a HUMAN {counterpart}, never Emily or the automated assistant. '
            'Each request contains Emily’s latest utterance. Use your supplied facts to answer it. '
            'After that, answer the current question instead of repeating your introduction or opening request. '
            'Use brief natural replies, occasional hesitation and the supplied personality. '
            'Aim to resolve this call in fewer than five replies from you and at most ten messages total across both speakers. '
            'Answer all requested details together using your facts; avoid repeating your complaint or adding unrelated questions. '
            'When asked for permission to discuss the prescription or coordinate follow-up, explicitly answer using contact_permission '
            'from your supplied scenario facts. Frustration is not refusal; do not withhold consent unless the scenario says to. '
            'Do not invent symptoms, references, approvals or facts; say you do not know when context is missing. '
            'Do not speak as the assistant or narrate the other speaker. You cannot change records or prescribe. '
            'Return JSON with your assigned speaker, observations=[], and end_call=true only when saying goodbye.\n'+json.dumps({
                'personality':scenario.get('personality'),
                'facts':human_facts,'prior_call_summary':data.get('prior_summary')}),counterpart_model,cancellation,
            opening={'situation':scenario.get('situation'),'objective':scenario['objective']})
        patient = facts.get('patient') or {}
        patient_name = ' '.join(filter(None,[patient.get('first_name'),patient.get('last_name')]))
        history = []
        feedback = ''
        max_turns = max(4,min(80,int(os.getenv('SIMULATION_MAX_TURNS','40'))))
        exhausted = True
        ending_reason = 'turn_limit'
        for index in range(max_turns):
            check()
            ai = index % 2 == 0
            speaker = assistant if ai else human
            instructions = {'first_turn':not speaker.spoken, 'turn_budget':{
                'your_reply_number':len(speaker.spoken)+1, 'total_message_number':index+1,
                'target_total_messages':10, 'hard_total_message_limit':max_turns}}
            if ai:
                instructions.update(workflow=workflow,validation_feedback=feedback)
            bind(stage='turn.generate', turn_index=index, speaker=speaker.role)
            log('turn.generate.started')
            result = speaker.respond(history[-1] if history else None,instructions,
                turn_schema(workflow['checklist'] if ai and index else []),patient_name=patient_name)
            check()
            speech = result['text']
            log('turn.generate.completed', characters=len(speech), end_call=result['end_call'],
                observation_count=len(result.get('observations', [])))
            bind(stage='turn.stream')
            turn_id = str(uuid4())
            pause(float(os.getenv('SIMULATION_PAUSE_SECONDS','0.3')))
            emit('transcript.started',transcript_id=turn_id,turn_index=index,speaker=speaker.role)
            for word_index, chunk in enumerate(words(speech),1):
                pause(float(os.getenv('SIMULATION_WORD_SECONDS','0.08')))
                emit('transcript.word',transcript_id=turn_id,word_index=word_index,delta=chunk)
            emit('transcript.completed',transcript_id=turn_id)
            log('turn.stream.completed', transcript_id=turn_id, word_count=word_index)
            history.append({'speaker':speaker.role,'text':speech})
            if ai and result.get('observations'):
                check()
                try:
                    bind(stage='observations.submit')
                    workflow = client.post(f'/conversations/{conversation_id}/observations',{'observations':result['observations']})
                    log('observations.accepted', workflow_status=workflow.get('status'))
                    feedback = ''
                except HTTPError as error:
                    log('observations.rejected', level=logging.WARNING, status_code=error.code)
                    if error.code not in (409,422): raise
                    feedback = 'Observation rejected. Use only current checklist action IDs, exact quotes from this call, and correctly typed result fields. Do not infer unknown facts.'
            if ai and index >= 4 and (result['end_call'] or workflow.get('status')=='intake_complete'):
                ending_reason='agent_end_call' if result['end_call'] else 'workflow_complete'
                exhausted = False
                break
        bind(stage='conversation.end', speaker=None, turn_index=None)
        log('conversation.ending', reason=ending_reason, turn_count=len(history), max_turns=max_turns)
        emit('conversation.ended')
        check()
        bind(stage='analysis.request')
        log('analysis.request.started')
        analysis = client.post(f'/conversations/{conversation_id}/analyze',{'turn_limit_reached':exhausted})
        check()
        log('analysis.request.completed', decision=analysis['decision'])
        if analysis['decision']=='continue':
            bind(stage='follow_up.dispatch')
            log('follow_up.dispatch.started')
            client.post(f'/conversations/{conversation_id}/dispatch',{})
        return conversation_id
    except Exception:
        try: client.post(f'/conversations/{conversation_id}/failed',{})
        except Exception:
            log('conversation.failure_report.failed', level=logging.ERROR, exc_info=True)
        raise
