"""Test adapter for validating replay with an in-memory clock and rollback transaction."""
from datetime import timedelta
from uuid import UUID
from unittest.mock import patch

from pydantic import TypeAdapter
from sqlalchemy import select

from server.app.crud.conversations import create_conversation, append_event
from server.models.conversation import ConversationAnalysis, Action, ConversationEvent
from server.schemas.conversation import ConversationCreate, ConversationEvent as EventSchema
from simulator.generate_conversation import generate_conversation


def replay_into_session(session, source, start):
    clock = [start]
    adapter = TypeAdapter(EventSchema)

    class Client:
        def create_conversation(self, metadata):
            return str(create_conversation(session, ConversationCreate(**metadata)).id)

        def send_event(self, conversation_id, event):
            append_event(session, UUID(conversation_id), adapter.validate_python(event))
            session.flush()

    def advance(seconds):
        clock[0] += timedelta(seconds=seconds)

    with patch('simulator.generate_conversation.timestamp', lambda: clock[0].isoformat()):
        record_id = generate_conversation(source.conversation_id, source.transcript, Client(), sleep=advance, name=source.name)
    analysis = session.scalar(select(ConversationAnalysis).where(ConversationAnalysis.conversation_record_id == UUID(record_id)))
    truth = source.transcript['ground_truth']
    # Synthetic history uses fixture labels, never inferred clinical conclusions.
    analysis.overall_sentiment = truth['overall_sentiment']
    analysis.reason_for_call = truth['reason_for_call']
    events = session.scalars(select(ConversationEvent).where(ConversationEvent.conversation_record_id == UUID(record_id))
                             .order_by(ConversationEvent.sequence)).all()
    action_ids = [UUID(event.data['action_id']) for event in events if event.data['type'] == 'action.simulated']
    for index, action_id in enumerate(action_ids):
        action = session.get(Action, action_id)
        action.previous_action = action_ids[index-1] if index else None
        action.next_action = action_ids[index+1] if index+1 < len(action_ids) else None
    session.flush()
    return UUID(record_id), clock[0]
