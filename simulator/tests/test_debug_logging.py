import json
import logging
import unittest
from unittest.mock import Mock

from simulator.debug_logging import JsonFormatter, log, log_context
from simulator.speaker import SpeakerAgent
from simulator.agent_conversation import turn_schema


class DiagnosticTests(unittest.TestCase):
    def test_exception_keeps_stack_and_type_without_sensitive_message(self):
        try:
            raise ValueError('secret patient transcript and token')
        except ValueError:
            with self.assertLogs('kyron.debug', level='ERROR') as captured:
                log('model.request.failed', level=logging.ERROR, exc_info=True, model_phase='parse_generated_json')
        output = JsonFormatter().format(captured.records[0])
        parsed = json.loads(output)
        self.assertEqual(parsed['error_type'], 'ValueError')
        self.assertEqual(parsed['model_phase'], 'parse_generated_json')
        self.assertTrue(parsed['traceback'][0]['frames'])
        self.assertNotIn('secret patient', output)

    def test_context_is_inherited_and_reset(self):
        with self.assertLogs('kyron.debug', level='INFO') as captured:
            with log_context(conversation_id='call-a'):
                log('outer')
                with log_context(turn_index=9): log('inner')
                log('outer-again')
            log('next-request')
        fields = [record.fields for record in captured.records]
        self.assertEqual(fields[1]['conversation_id'], 'call-a')
        self.assertEqual(fields[1]['turn_index'], 9)
        self.assertNotIn('turn_index', fields[2])
        self.assertNotIn('conversation_id', fields[3])

    def test_repetition_retries_log_reason_and_exhaustion_without_speech(self):
        speech = 'Private fictional patient sentence repeated for validation testing.'
        model = Mock()
        model.generate.return_value = {'speaker':'patient', 'text':speech, 'end_call':False, 'observations':[]}
        agent = SpeakerAgent('patient', 'Private prompt.', model)
        with self.assertLogs('kyron.debug', level='WARNING') as captured:
            with self.assertRaises(ValueError):
                agent.respond({'speaker':'ai_agent','text':speech}, {}, turn_schema([]))
        events = [json.loads(JsonFormatter().format(record)) for record in captured.records]
        self.assertEqual([event['attempt'] for event in events], [1, 2, 3])
        self.assertTrue(events[-1]['exhausted'])
        self.assertIn('copied', events[-1]['reason'])
        self.assertNotIn(speech, json.dumps(events))


class SchemaCompatibilityTests(unittest.TestCase):
    def test_refs_are_inlined_without_losing_required_fields_or_enums(self):
        from simulator.local_model import inference_schema
        schema={'$defs':{'Choice':{'type':'object','properties':{'title':{'type':'string','maxLength':2000},
                'status':{'type':'string','enum':['done','pending']}},'required':['title','status']}},
                'type':'object','properties':{'result':{'$ref':'#/$defs/Choice'},'actions':{'type':'array','maxItems':0,'items':{'type':'object'}}},'required':['result']}
        converted=inference_schema(schema)
        self.assertNotIn('$defs',converted)
        self.assertEqual(converted['properties']['result']['properties']['title'],{'type':'string'})
        self.assertEqual(converted['properties']['result']['required'],['title','status'])
        self.assertEqual(converted['properties']['result']['properties']['status']['enum'],['done','pending'])
        self.assertEqual(converted['properties']['actions']['maxItems'],0)
        self.assertIn('maxLength',schema['$defs']['Choice']['properties']['title'])
