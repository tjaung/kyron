"""Persist each accepted event and its derived conversation state atomically."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, text

from server.models.context import Patient, PatientPractice, Practice, Prescription, ProviderPractice, Provider
from server.models.conversation import (
    Action, ConversationAnalysis, ConversationEvent, ConversationRecord, ConversationTranscript,
)
from server.models.simulation import SimulationConversation
from server.models.workflow import ActionDefinition


def require(condition, message, status=409):
    if not condition:
        raise HTTPException(status, message)


def lock_event_writer(session):
    # Serialize event inserts through commit. SSE IDs cannot skip a lower ID
    # whose transaction has not committed yet, even with concurrent requests.
    session.execute(text("SELECT pg_advisory_xact_lock(714203)"))


def create_conversation(session, payload):
    lock_event_writer(session)
    practice = session.get(Practice, payload.practice_id)
    require(practice is not None, "Practice not found", 404)
    source = session.get(SimulationConversation, payload.source_conversation_id)
    require(source is not None, "Source conversation not found", 404)
    links = source.context["metadata"]
    for key in ("practice_id", "patient_practice_id", "prescription_id"):
        supplied = getattr(payload, key)
        expected = UUID(links[key]) if links.get(key) else None
        require(supplied == expected, f"{key} does not match the source conversation", 422)
    patient = None
    if payload.patient_practice_id:
        registration = session.get(PatientPractice, payload.patient_practice_id)
        require(registration is not None, "Patient registration not found", 404)
        require(registration.practice_id == payload.practice_id, "Patient belongs to another practice", 422)
        patient = session.get(Patient, registration.patient_id)
    prescription = None
    if payload.prescription_id:
        prescription = session.get(Prescription, payload.prescription_id)
        require(prescription is not None, "Prescription not found", 404)
        require(prescription.patient_practice_id == payload.patient_practice_id,
                "Prescription does not match the patient registration", 422)
    affiliation = session.get(ProviderPractice, prescription.prescriber_provider_practice_id) if prescription else None
    if affiliation is None and payload.provider_practice_id:
        affiliation = session.get(ProviderPractice, payload.provider_practice_id)
        require(affiliation is not None, "Provider affiliation not found", 404)
    if affiliation:
        require(affiliation.practice_id == practice.practice_id, "Provider belongs to another practice", 422)
    derived = {"patient_id": patient.patient_id if patient else None,
               "provider_id": affiliation.provider_id if affiliation else None,
               "provider_practice_id": affiliation.provider_practice_id if affiliation else None}
    for key, expected in derived.items():
        supplied = getattr(payload, key)
        require(supplied is None or supplied == expected, f"{key} does not match the linked records", 422)
        require(not links.get(key) or UUID(links[key]) == expected, f"Source {key} does not match the linked records", 422)
    runtime_name = source.name
    if payload.parent_conversation_id:
        parent = session.get(ConversationRecord,payload.parent_conversation_id)
        require(parent is not None and parent.source_conversation_id == payload.source_conversation_id,
                "Invalid parent conversation", 422)
        analysis = session.scalar(select(ConversationAnalysis).where(ConversationAnalysis.conversation_record_id == parent.id))
        require(analysis is not None and analysis.decision == 'continue', 'Parent has no continuation decision')
        existing = session.scalar(select(ConversationRecord).where(ConversationRecord.parent_conversation_id == parent.id))
        if existing: return existing
        from server.app.services.agent import publish
        runtime_name = f"{source.context['metadata'].get('scenario_name',source.name)} · {analysis.next_action['target'].replace('_',' ')} follow-up"
        task_id=analysis.next_action.get('task_id')
        if task_id:
            from server.models.conversation import ActionTask
            task=session.get(ActionTask,UUID(task_id))
            if task: task.status='running'
        parent.status = 'continued'
        publish(session,parent,'conversation.finalized',status='continued')
    record = ConversationRecord(
        **payload.model_dump(exclude={"name", *derived}), **derived, name=runtime_name,
    )
    session.add(record)
    session.flush()
    if payload.parent_conversation_id and analysis.next_action.get('task_id'):
        task=session.get(ActionTask,UUID(analysis.next_action['task_id']))
        if task: task.result={'simulated':True,'conversation_id':str(record.id)}
    session.add(ConversationAnalysis(conversation_record_id=record.id))
    metadata = {
        **payload.model_dump(mode="json"), "id": str(record.id), "name": record.name,
        "practice_name": practice.name,
        **{key: str(value) if value else None for key, value in derived.items()},
        "provider_name": (lambda provider: f"{provider.first_name} {provider.last_name}")(session.get(Provider, affiliation.provider_id)) if affiliation else None,
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else None,
        "medication_name": prescription.medication_name if prescription else None,
        "scenario_name": links.get("scenario_name", source.name),
        "next_conversation": str(source.next_conversation) if source.next_conversation else None,
    }
    session.add(ConversationEvent(conversation_record_id=record.id, sequence=0, data={
        "type": "conversation.created", "conversation_id": str(record.id), "metadata": metadata,
    }))
    return record


def append_event(session, conversation_id, event):
    lock_event_writer(session)
    record = session.get(ConversationRecord, conversation_id)
    require(record is not None, "Conversation not found", 404)
    data = {**event.model_dump(mode="json"), "conversation_id": str(conversation_id)}
    existing = session.scalar(select(ConversationEvent).where(
        ConversationEvent.conversation_record_id == conversation_id,
        ConversationEvent.sequence == event.sequence,
    ))
    if existing:
        require(existing.data == data, "Sequence already contains a different event")
        return
    require(record.status != "completed", "Replay already completed")
    require(event.sequence == record.last_sequence + 1, "Events must arrive in sequence")
    require(event.occurred_at >= record.start_time, "Event predates conversation")
    transcript_id = getattr(event, "transcript_id", None)
    turn = session.get(ConversationTranscript, transcript_id) if transcript_id else None
    if event.type == "transcript.started":
        require(record.status == "live", "Call already ended")
        require(turn is None, "Transcript ID already exists")
        count = session.scalar(select(func.count()).select_from(ConversationTranscript).where(
            ConversationTranscript.conversation_record_id == conversation_id,
        ))
        require(event.turn_index == count, "Turns must arrive in order")
        active = session.scalar(select(ConversationTranscript).where(
            ConversationTranscript.conversation_record_id == conversation_id,
            ConversationTranscript.end_time.is_(None),
        ))
        require(active is None, "Previous turn is still speaking")
        session.add(ConversationTranscript(
            transcript_id=event.transcript_id, conversation_record_id=conversation_id,
            speaker=event.speaker, turn_index=event.turn_index, start_time=event.occurred_at,
        ))
    elif event.type in ("transcript.word", "transcript.completed"):
        require(turn is not None and turn.conversation_record_id == conversation_id,
                "Transcript does not belong to this conversation", 422)
        require(record.status == "live" and turn.end_time is None, "Transcript is closed")
        require(event.occurred_at >= turn.start_time, "Event predates transcript")
        if event.type == "transcript.word":
            require(event.word_index == turn.last_word_index + 1, "Words must arrive in order")
            turn.transcript += event.delta
            turn.last_word_index = event.word_index
        else:
            turn.end_time = event.occurred_at
    elif event.type == "action.simulated":
        if transcript_id:
            require(turn is not None and turn.conversation_record_id == conversation_id,
                    "Action transcript does not belong to this conversation", 422)
            require(record.status == "live" and turn.end_time is None, "Turn action arrived after its turn")
            require(turn.action is None, "A turn can have at most one action")
        else:
            require(record.status == "ended", "Post-call action arrived before the call ended")
        require(session.get(Action, event.action_id) is None, "Action ID already exists")
        analysis_id = session.scalar(select(ConversationAnalysis.analysis_id).where(
            ConversationAnalysis.conversation_record_id == conversation_id,
        ))
        definition = session.scalar(select(ActionDefinition).where(ActionDefinition.code == event.action).order_by(ActionDefinition.version.desc()))
        session.add(Action(action_id=event.action_id, action_definition_id=definition.action_id if definition else None, analysis_id=analysis_id,
                           transcript_id=transcript_id, action=event.action, reason=event.reason))
        if turn:
            turn.action = event.action_id
    elif event.type == "conversation.ended":
        require(record.status == "live", "Call already ended")
        active = session.scalar(select(ConversationTranscript).where(
            ConversationTranscript.conversation_record_id == conversation_id,
            ConversationTranscript.end_time.is_(None),
        ))
        require(active is None, "A transcript is still open")
        record.end_time = event.occurred_at
        record.status = "ended"
    elif event.type == "replay.completed":
        require(record.status == "ended", "Call has not ended")
        record.status = "completed"
    record.last_sequence = event.sequence
    session.add(ConversationEvent(conversation_record_id=conversation_id,
                                  sequence=event.sequence, data=data))


def events_after(session, cursor, practice_id, conversation_id=None):
    rows = session.scalars(select(ConversationEvent).join(
        ConversationRecord, ConversationRecord.id == ConversationEvent.conversation_record_id,
    ).where(
        ConversationEvent.id > cursor,
        ConversationRecord.practice_id == practice_id,
        *([ConversationRecord.id == conversation_id] if conversation_id else []),
    ).order_by(ConversationEvent.id).limit(500))
    return [{"id": row.id, "data": row.data} for row in rows]
