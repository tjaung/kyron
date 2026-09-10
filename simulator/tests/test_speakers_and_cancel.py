import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch
from uuid import uuid4
from simulator.speaker import SpeakerAgent
from simulator.cancellation import Cancellation, SimulationCancelled
from simulator.local_model import LocalModel
from simulator.agent_conversation import generate_agent_conversation, turn_schema
from simulator.main import Simulator
from simulator.tests.test_agent_conversation import AgentConversationTests
from simulator.tests.test_simulator import Transaction


class SpeakerTests(unittest.TestCase):
    def test_copy_is_retried_without_becoming_a_turn_or_history(self):
        speech = "I'm Casey Rivera and I need help with my delayed prescription because the pharmacy could not fill it."
        model = Mock()
        correct = {'speaker':'ai_agent','text':'I can help. Could you confirm your date of birth?','end_call':False,'observations':[]}
        model.generate.side_effect = [dict(correct,text=speech),correct]
        agent = SpeakerAgent('ai_agent','You are Emily.',model)
        result = agent.respond({'speaker':'patient','text':speech},{},turn_schema([]),patient_name='Casey Rivera')
        self.assertEqual(result,correct)
        self.assertEqual(agent.spoken,[correct['text']])
        self.assertEqual(model.generate.call_count,2)
        self.assertEqual(len([m for m in agent.messages if m['role']=='assistant']),1)

    def test_persistent_copy_and_wrong_identity_fail_before_streaming(self):
        model = Mock()
        model.generate.return_value = {'speaker':'ai_agent','text':"My name is Casey Rivera and I need my prescription.",'end_call':False,'observations':[]}
        agent = SpeakerAgent('ai_agent','You are Emily.',model)
        with self.assertRaises(ValueError):
            agent.respond({'speaker':'patient','text':'Can you help?'},{},turn_schema([]),patient_name='Casey Rivera')
        self.assertEqual(model.generate.call_count,3)
        self.assertEqual(agent.spoken,[])
        self.assertEqual(agent.messages,[])

    def test_human_receives_latest_speech_and_opening_only_once(self):
        for role in ('patient', 'provider', 'pharmacy', 'insurance_agent'):
            with self.subTest(role=role):
                model = Mock()
                model.generate.side_effect = [
                    {'speaker':role,'text':'I am calling about a delayed prescription.','end_call':False,'observations':[]},
                    {'speaker':role,'text':'My number is 555-0100, and I use Cedar Pharmacy.','end_call':False,'observations':[]},
                ]
                agent = SpeakerAgent(role,'Your supplied facts.',model,opening={'situation':'opening scenario only'})
                agent.respond({'speaker':'ai_agent','text':'How can I help?'},{'first_turn':True},turn_schema([]))
                latest = 'Could you confirm your phone number and pharmacy?'
                agent.respond({'speaker':'ai_agent','text':latest},{'first_turn':False},turn_schema([]))
                first, second = model.generate.call_args_list
                self.assertIn('opening scenario only',first.args[0])
                self.assertNotIn('opening scenario only',second.args[0])
                self.assertEqual(second.args[1], [
                    {'role':'user','content':'How can I help?'},
                    {'role':'assistant','content':'I am calling about a delayed prescription.'},
                    {'role':'user','content':latest},
                ])
                self.assertNotIn('I am calling about a delayed prescription.',second.args[0])
                self.assertEqual(agent.messages[-2],{'role':'user','content':latest})

    def test_qwen_json_generation_closes_reasoning_before_output(self):
        for name in ('qwen3:4b', 'another-model:small'):
            with self.subTest(name=name), patch('simulator.local_model.http.client.HTTPConnection') as connection_type:
                connection = connection_type.return_value
                response = connection.getresponse.return_value
                response.status = 200
                response.read.return_value = json.dumps({'message':{'content':'{"text":"My number is 555-0100."}'}}).encode()
                model = LocalModel()
                model.url = 'http://localhost:11434'
                model.name = name
                messages = [{'role':'user','content':'What is your phone number?'}]
                model.generate('You are the patient.',messages,{})
                payload = json.loads(connection.request.call_args.kwargs['body'])
                self.assertFalse(payload['think'])
                if name.startswith('qwen3:'):
                    self.assertEqual(payload['messages'][-1],{'role':'assistant','content':'<think>\n\n</think>\n\n'})
                else:
                    self.assertEqual(payload['messages'][-1],messages[-1])
                self.assertEqual(len(messages),1)

    def test_model_request_can_be_cancelled_while_waiting_for_response(self):
        entered, release = threading.Event(),threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                entered.set(); release.wait(5)
                try:
                    self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
                except OSError: pass
            def log_message(self,*args): pass
        server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        listener = threading.Thread(target=server.serve_forever); listener.start()
        model = LocalModel(); model.url=f'http://127.0.0.1:{server.server_port}'
        cancellation = Cancellation(); errors=[]
        def generate():
            try: model.generate('test',[],{},cancellation=cancellation)
            except Exception as error: errors.append(error)
        worker=threading.Thread(target=generate)
        try:
            worker.start(); self.assertTrue(entered.wait(2))
            cancellation.cancel(); worker.join(1)
            self.assertFalse(worker.is_alive())
            self.assertIsInstance(errors[0],SimulationCancelled)
        finally:
            release.set(); worker.join(3); server.shutdown(); server.server_close(); listener.join()

    def test_cancel_stops_words_and_skips_analysis(self):
        client=AgentConversationTests().client()
        cancellation=Cancellation()
        client.send_event.side_effect=lambda id,event: cancellation.cancel() if event['type']=='transcript.word' else None
        model=Mock()
        model.generate.return_value={'speaker':'ai_agent','text':'Hello there, how can I help?','end_call':False,'observations':[]}
        with self.assertRaises(SimulationCancelled):
            generate_agent_conversation(uuid4(),{'metadata':{}},client,model=model,cancellation=cancellation,sleep=lambda _:None)
        kinds=[call.args[1]['type'] for call in client.send_event.call_args_list]
        self.assertEqual(kinds,['transcript.started','transcript.word'])
        self.assertFalse(any(call.args[0].endswith('/analyze') for call in client.post.call_args_list))

    def test_worker_cancel_is_scoped_and_rolls_back_source(self):
        transaction=Transaction({'metadata':{}})
        app=Simulator(None,lambda:transaction)
        entered=threading.Event()
        def generate(*args,**kwargs):
            kwargs['on_created']('active-id'); entered.set(); kwargs['cancellation'].wait(10)
        with patch('simulator.main.generate_agent_conversation',side_effect=generate):
            app.trigger(); self.assertTrue(entered.wait(2))
            self.assertFalse(app.cancel('different-id'))
            self.assertTrue(app.cancel('active-id'))
            app.worker.join(1)
        self.assertFalse(app.worker.is_alive())
        self.assertEqual(app.status()['status'],'failed')
        self.assertTrue(transaction.rolled_back)
        self.assertFalse(transaction.used)
