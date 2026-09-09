"""Persist each accepted event and its derived conversation state atomically."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, text

from server.models.context import Patient, PatientPractice, Practice, Prescription
from server.models.conversation import (
    Action, ConversationAnalysis, ConversationEvent, ConversationRecord, ConversationTranscript,
)
from server.models.simulation import SimulationConversation


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
    links = source.transcript["metadata"]
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
    record = ConversationRecord(
        **payload.model_dump(exclude={"name"}), name=source.name,
    )
    session.add(record)
    session.flush()
    session.add(ConversationAnalysis(conversation_record_id=record.id))
    metadata = {
        **payload.model_dump(mode="json"), "id": str(record.id), "name": source.name,
        "practice_name": practice.name,
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
        session.add(Action(action_id=event.action_id, analysis_id=analysis_id,
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


def events_after(session, cursor, practice_id):
    rows = session.scalars(select(ConversationEvent).join(
        ConversationRecord, ConversationRecord.id == ConversationEvent.conversation_record_id,
    ).where(
        ConversationEvent.id > cursor,
        ConversationRecord.practice_id == practice_id,
    ).order_by(ConversationEvent.id).limit(500))
    return [{"id": row.id, "data": row.data} for row in rows]
