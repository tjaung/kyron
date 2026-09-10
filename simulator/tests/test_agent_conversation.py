import unittest
import os
import json
from unittest.mock import Mock, patch
from uuid import uuid4
from simulator.agent_conversation import generate_agent_conversation
from simulator.main import Simulator


class AgentConversationTests(unittest.TestCase):
    def client(self, decision='stop'):
        client = Mock()
        client.create_conversation.return_value = str(uuid4())
        def post(path, payload):
            if path.endswith('/agent-context'):
                return {'scenario':{'objective':'Help with prescription','counterpart':'patient'},'facts':{'patient':{'name':'Avery'},'authorizations':['private payer data']},'workflow':{'status':'active','checklist':[]}}
            if path.endswith('/analyze'): return {'decision':decision}
            return {}
        client.post.side_effect = post
        return client

    def test_roles_word_stream_analysis_and_conditional_dispatch(self):
        for decision in ('continue','stop'):
            client = self.client(decision)
            model = Mock()
            model.generate.side_effect = [{'speaker':'ai_agent' if i%2==0 else 'patient','text':text,'end_call':i==4,'observations':[]} for i,text in enumerate([
                'Hello! How can I help?', 'I need my prescription.', 'Can you confirm your name?', 'Avery Chen.', 'Thank you. Goodbye.'])]
            generate_agent_conversation(uuid4(),{'metadata':{'practice_id':str(uuid4())}},client,model=model,sleep=lambda _:None)
            events = [c.args[1] for c in client.send_event.call_args_list]
            self.assertEqual([e['sequence'] for e in events],list(range(1,len(events)+1)))
            self.assertEqual(events[0]['speaker'],'ai_agent')
            self.assertEqual(events[-1]['type'],'conversation.ended')
            self.assertNotIn('replay.completed',[e['type'] for e in events])
            self.assertNotIn('private payer data',model.generate.call_args_list[1].args[0])
            import json
            ai_history = model.generate.call_args_list[2].args[1]
            human_history = model.generate.call_args_list[3].args[1]
            self.assertEqual([json.loads(m['content'])['speaker'] for m in ai_history if m['role']=='assistant'],['ai_agent'])
            self.assertEqual([m['content'] for m in human_history if m['role']=='assistant'],['I need my prescription.'])
            self.assertNotIn('I need my prescription.',model.generate.call_args_list[3].args[0])
            self.assertTrue(human_history[-1]['content'].endswith('Can you confirm your name?'))
            self.assertEqual(json.loads(ai_history[-1]['content'])['other_speaker']['speaker'],'patient')
            paths = [c.args[0] for c in client.post.call_args_list]
            self.assertEqual(any(p.endswith('/dispatch') for p in paths),decision=='continue')

    def test_message_target_is_soft_and_default_safety_limit_is_forty(self):
        client = self.client()
        model = Mock()
        model.generate.side_effect = [
            {'speaker':'ai_agent' if i % 2 == 0 else 'patient',
             'text':f'Turn {i}: still discussing the required details.', 'end_call':False, 'observations':[]}
            for i in range(40)]
        with patch.dict(os.environ):
            os.environ.pop('SIMULATION_MAX_TURNS', None)
            generate_agent_conversation(uuid4(), {'metadata':{}}, client, model=model, sleep=lambda _:None)
        self.assertEqual(model.generate.call_count, 40)
        analysis = next(call for call in client.post.call_args_list if call.args[0].endswith('/analyze'))
        self.assertTrue(analysis.args[1]['turn_limit_reached'])
        assistant_call, human_call = model.generate.call_args_list[-2:]
        budget = json.loads(assistant_call.args[1][-1]['content'])['turn_instructions']['turn_budget']
        self.assertEqual(budget, {'your_reply_number':20, 'total_message_number':39,
                                 'target_total_messages':10, 'hard_total_message_limit':40})
        self.assertIn('fewer than five replies', assistant_call.args[0])
        self.assertIn('fewer than five replies', human_call.args[0])
        self.assertIn('"total_message_number": 40', human_call.args[0])

    def test_invalid_model_output_marks_failed(self):
        client = self.client()
        model = Mock()
        model.generate.return_value = {'text':'','end_call':False}
        with self.assertRaises(ValueError):
            generate_agent_conversation(uuid4(),{'metadata':{}},client,model=model,sleep=lambda _:None)
        self.assertTrue(client.post.call_args.args[0].endswith('/failed'))

    def test_worker_only_continues_when_server_dispatches_and_commits_each_call(self):
        from simulator.tests.test_simulator import Transaction
        first,second = Transaction({'metadata':{}}),Transaction({'metadata':{}})
        first.source['name'] = second.source['name'] = 'Scenario'
        second.source['conversation_id'] = first.source['conversation_id']
        connections = iter([first,second])
        app = Simulator(None,lambda:next(connections))
        calls = []
        def generate(source_id,*args,**kwargs):
            kwargs['on_created']('parent-id')
            calls.append(kwargs.get('parent_id'))
            if len(calls)==1:
                self.assertTrue(app.continue_call(str(source_id),'parent-id'))
            return 'runtime-id'
        with patch('simulator.main.generate_agent_conversation',side_effect=generate):
            app.run(None)
        self.assertEqual(calls,[None,'parent-id'])
        self.assertTrue(first.used and second.used)
        self.assertEqual(app.status()['status'],'completed')
