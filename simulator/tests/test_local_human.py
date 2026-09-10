"""Opt-in real-model regression: RUN_LOCAL_MODEL_TESTS=1, local Ollama required."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from simulator.agent_conversation import generate_agent_conversation
from simulator.local_model import LocalModel


@unittest.skipUnless(os.getenv('RUN_LOCAL_MODEL_TESTS') == '1', 'requires local Ollama')
class LocalHumanTests(unittest.TestCase):
    def test_human_answers_latest_contact_and_identity_questions(self):
        data = Path(__file__).resolve().parents[2] / 'server' / 'data'
        source = next(row for row in json.loads((data / 'conversations.json').read_text())
                      if row['conversation_id'] == 'c54f332c-c47f-589e-8516-6a55c894542d')
        records = json.loads((data / 'context.json').read_text())
        links = source['context']['metadata']
        facts = {name: next(row for row in records[group] if row[key] == links[key])
                 for name, group, key in [('patient', 'patients', 'patient_id'),
                                          ('practice', 'practices', 'practice_id'),
                                          ('prescription', 'prescriptions', 'prescription_id')]}
        questions = ["Hello! I'm Emily from Cedar Primary Care. How can I help you today?",
                     "Thank you for reaching out, Casey. I can see your prescription for Budesonide-formoterol was written on February 1, 2026, and it's currently active with 30 days supply and 2 refills remaining. To help resolve the delay, could you confirm your phone number and the pharmacy you'd like to use for pickup?",
                     'Thank you. Could you confirm your full name and date of birth, and may we discuss this prescription?']
        for attempt in range(3):
            with self.subTest(attempt=attempt), patch.dict(os.environ, {'SIMULATION_MAX_TURNS':'6'}):
                client, assistant = Mock(), Mock()
                turns = []
                client.create_conversation.return_value = str(uuid4())
                def post(path, payload):
                    if path.endswith('/agent-context'):
                        return {'scenario':source['context'], 'facts':facts,
                                'workflow':{'status':'active', 'checklist':[]}}
                    if path.endswith('/analyze'): return {'decision':'stop'}
                    return {}
                def event(record_id, value):
                    if value['type'] == 'transcript.started': turns.append('')
                    if value['type'] == 'transcript.word': turns[-1] += value['delta']
                client.post.side_effect = post
                client.send_event.side_effect = event
                assistant.generate.side_effect = [
                    {'speaker':'ai_agent', 'text':question, 'end_call':False, 'observations':[]}
                    for question in questions]
                generate_agent_conversation(source['conversation_id'], source['context'], client,
                                            model=assistant, human_model=LocalModel(), sleep=lambda _:None)
                digits = lambda text: ''.join(c for c in text if c.isdigit())
                self.assertIn(digits(facts['patient']['phone']), digits(turns[3]))
                self.assertIn(facts['prescription']['pharmacy_name'].lower(), turns[3].lower())
                self.assertIn('Casey Rivera', turns[5])
                self.assertTrue('1983' in turns[5] and ('April' in turns[5] or '04' in turns[5]), turns[5])
