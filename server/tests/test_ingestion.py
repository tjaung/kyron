"""PostgreSQL-backed API tests. Each test rolls back all of its runtime records."""

from datetime import datetime, timezone
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from server.app.main import app
from server.core.database import engine, get_session
from server.core.config import settings
from server.core.seed import initialize_database, seed
from server.models.context import Practice
from server.models.conversation import Action, ConversationEvent, ConversationRecord, ConversationTranscript
from server.models.simulation import SimulationConversation


class IngestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()

    def setUp(self):
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.session = Session(bind=self.connection)
        app.dependency_overrides[get_session] = lambda: self.session
        self.client = TestClient(app, headers={"Authorization": f"Bearer {settings.simulator_token}"})
        self.source = self.session.scalar(select(SimulationConversation).order_by(SimulationConversation.name))
        links = self.source.transcript["metadata"]
        self.metadata = {key: links[key] for key in ("practice_id", "patient_practice_id", "prescription_id")}
        self.metadata.update(source_conversation_id=str(self.source.conversation_id), start_time=self.now())

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    def create(self):
        response = self.client.post("/api/conversations", json=self.metadata)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def send(self, conversation_id, sequence, event_type, **fields):
        return self.client.post(f"/api/conversations/{conversation_id}/events", json={
            "type": event_type, "sequence": sequence, "occurred_at": self.now(), **fields,
        })

    def test_stream_persists_words_actions_and_completion(self):
        runtime = self.create()
        turn = str(uuid4())
        self.assertEqual(self.send(runtime, 1, "transcript.started", transcript_id=turn,
                                   turn_index=0, speaker="patient").status_code, 204)
        word = {"type": "transcript.word", "sequence": 2, "occurred_at": self.now(),
                "transcript_id": turn, "word_index": 1, "delta": "Hello, "}
        path = f"/api/conversations/{runtime}/events"
        self.assertEqual(self.client.post(path, json=word).status_code, 204)
        self.assertEqual(self.client.post(path, json=word).status_code, 204)
        self.assertEqual(self.client.post(path, json={**word, "delta": "Different"}).status_code, 409)
        action_id = str(uuid4())
        self.assertEqual(self.send(runtime, 3, "action.simulated", action_id=action_id,
            transcript_id=turn, action="review_record", reason="Verify context", simulated=True).status_code, 204)
        self.assertEqual(self.send(runtime, 4, "transcript.completed", transcript_id=turn).status_code, 204)
        self.assertEqual(self.send(runtime, 5, "conversation.ended").status_code, 204)
        self.assertEqual(self.send(runtime, 6, "action.simulated", action_id=str(uuid4()),
            transcript_id=None, action="call_insurance", reason="Check authorization", simulated=True).status_code, 204)
        self.assertEqual(self.send(runtime, 7, "replay.completed").status_code, 204)
        record = self.session.get(ConversationRecord, runtime)
        transcript = self.session.get(ConversationTranscript, turn)
        self.assertEqual(record.status, "completed")
        self.assertEqual(transcript.transcript, "Hello, ")
        self.assertEqual(str(transcript.action), action_id)
        self.assertEqual(str(self.session.get(Action, action_id).transcript_id), turn)
        events = self.session.scalars(select(ConversationEvent).where(
            ConversationEvent.conversation_record_id == runtime,
        ).order_by(ConversationEvent.sequence)).all()
        self.assertEqual(len(events), 8)
        self.assertEqual(events[0].data["type"], "conversation.created")
        self.assertNotIn("turns", events[0].data["metadata"])

    def test_invalid_order_and_foreign_transcript_are_rejected(self):
        first, second = self.create(), self.create()
        turn = str(uuid4())
        self.assertEqual(self.send(first, 2, "conversation.ended").status_code, 409)
        self.assertEqual(self.send(first, 1, "transcript.started", transcript_id=turn,
            turn_index=0, speaker="patient").status_code, 204)
        self.assertEqual(self.send(second, 1, "transcript.word", transcript_id=turn,
            word_index=1, delta="Wrong call").status_code, 422)
        self.assertEqual(self.send(first, 2, "transcript.word", transcript_id=turn,
            word_index=3, delta="Skipped words").status_code, 409)
        self.assertEqual(self.send(first, 2, "conversation.ended").status_code, 409)

    def test_practice_mismatch_and_invalid_events_are_rejected(self):
        other = self.session.scalar(select(Practice).where(Practice.practice_id != self.metadata["practice_id"]))
        response = self.client.post("/api/conversations", json={**self.metadata, "practice_id": str(other.practice_id)})
        self.assertEqual(response.status_code, 422)
        runtime = self.create()
        response = self.send(runtime, 1, "unknown.event")
        self.assertEqual(response.status_code, 422)

    def test_seeding_preserves_used_sources(self):
        before = self.session.scalar(select(func.count()).select_from(SimulationConversation))
        self.source.is_used = True
        self.session.flush()
        seed(self.session)
        self.session.flush()
        after = self.session.scalar(select(func.count()).select_from(SimulationConversation))
        self.assertEqual(before, after)
        self.assertTrue(self.session.get(SimulationConversation, self.source.conversation_id).is_used)


if __name__ == "__main__":
    unittest.main()
