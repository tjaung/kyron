"""Model responses are deterministic doubles; SQL, auth, events and checklist evaluation are real."""
from unittest.mock import patch, AsyncMock
from uuid import UUID, uuid4
from sqlalchemy import select
from server.tests.test_ingestion import IngestionTests
from server.models.conversation import ConversationAnalysis, ConversationRecord, Action
from server.models.workflow import WorkflowRun
from server.core.workflow_seed import key


class AgentTests(IngestionTests):
    def prepare(self):
        conversation = self.create()
        base = '/api/conversations/' + conversation
        context = self.client.post(base+'/agent-context',json={})
        self.assertEqual(context.status_code,200,context.text)
        # Existing prescription runs must remain resumable after intake is introduced.
        run=self.session.scalar(select(WorkflowRun).where(WorkflowRun.conversation_id==UUID(conversation)))
        run.workflow_id=key('workflow','new_prescription'); run.current_rule_id=key('rule','identity')
        self.session.flush()
        turn = str(uuid4())
        self.send(conversation,1,'transcript.started',transcript_id=turn,turn_index=0,speaker='patient')
        self.send(conversation,2,'transcript.word',transcript_id=turn,word_index=1,delta='I am Avery Chen, born April 12 1980. You may discuss my prescription.')
        self.send(conversation,3,'transcript.completed',transcript_id=turn)
        return conversation,base

    def output(self, next_action=None):
        return {'summary':'The caller requested help filling a prescription. Further verification remains necessary.',
                'overall_sentiment':'neutral','reason_for_call':'Prescription request','actions_needed':['Verify the request'],
                'next_action':next_action}

    def test_analysis_is_saved_before_dispatch_and_followup_carries_progress(self):
        conversation,base = self.prepare()
        observation = {'action_id':str(key('action','verify_identity')),'status':'completed',
            'result':{'verified':True,'contact_permission':True,'evidence':'Two identifiers and permission'},
            'evidence':'I am Avery Chen, born April 12 1980. You may discuss my prescription.'}
        response = self.client.post(base+'/observations',json={'observations':[observation]})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['current_rule_id'],str(key('rule','urgency')))
        self.assertEqual(len(self.session.scalars(select(Action).join(ConversationAnalysis,Action.analysis_id==ConversationAnalysis.analysis_id).where(ConversationAnalysis.conversation_record_id==UUID(conversation))).all()),1)
        self.send(conversation,4,'conversation.ended')
        next_action = {'target':'patient','objective':'Ask the patient about urgency','action_id':str(key('action','assess_urgency'))}
        with patch('server.app.api.agent.LocalModel.generate',return_value=self.output(next_action)) as model:
            response = self.client.post(base+'/analyze',json={})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['decision'],'continue')
            self.assertEqual(self.client.post(base+'/analyze',json={}).status_code,200)
            self.assertEqual(model.call_count,1)
        analysis = self.session.scalar(select(ConversationAnalysis).where(ConversationAnalysis.conversation_record_id==UUID(conversation)))
        self.assertTrue(analysis.analyzed_at)
        self.assertEqual(analysis.metrics['validated_actions'],1)
        async def dispatch(method,path,**kwargs):
            self.assertEqual(path,'/continue')
            self.assertEqual(analysis.decision,'continue')
            self.assertEqual(kwargs['json']['parent_conversation_id'],conversation)
            return {'status':'accepted'}
        with patch('server.app.api.agent.simulator_request',side_effect=dispatch):
            self.assertEqual(self.client.post(base+'/dispatch').status_code,200)
        child_metadata = {**self.metadata,'parent_conversation_id':conversation,'start_time':self.now()}
        first = self.client.post('/api/conversations',json=child_metadata)
        second = self.client.post('/api/conversations',json=child_metadata)
        self.assertEqual(first.json(),second.json())
        child = self.client.post('/api/conversations/'+first.json()['id']+'/agent-context',json={})
        self.assertEqual(child.json()['workflow']['current_rule_id'],str(key('rule','urgency')))
        self.assertEqual(child.json()['workflow']['completed_rules'],[str(key('rule','identity'))])
        with patch('server.app.api.agent.simulator_request',new_callable=AsyncMock) as dispatch:
            self.assertEqual(self.client.post(base+'/dispatch').json()['status'],'already_started')
            dispatch.assert_not_called()

    def test_no_evidence_unknown_action_and_turn_limit_never_complete_work(self):
        conversation,base = self.prepare()
        response = self.client.post(base+'/observations',json={'observations':[{'action_id':str(uuid4()),'status':'completed','result':{},'evidence':'invented'}]})
        self.assertEqual(response.status_code,422)
        self.send(conversation,4,'conversation.ended')
        with patch('server.app.api.agent.LocalModel.generate',return_value=self.output({'target':'patient','objective':'Verify patient identity','action_id':str(key('action','verify_identity'))})):
            result = self.client.post(base+'/analyze',json={'turn_limit_reached':True})
        self.assertEqual(result.json()['decision'],'needs_review')
        self.assertEqual(self.client.post(base+'/dispatch').json()['status'],'stopped')

    def test_terminal_workflow_stops_and_analysis_failure_is_visible(self):
        conversation,base = self.prepare()
        run = self.session.scalar(select(WorkflowRun).where(WorkflowRun.conversation_id==UUID(conversation)))
        run.status = 'identity_unverified'
        self.session.flush()
        self.send(conversation,4,'conversation.ended')
        with patch('server.app.api.agent.LocalModel.generate',return_value=self.output()):
            self.assertEqual(self.client.post(base+'/analyze',json={}).json()['decision'],'stop')
        self.assertEqual(self.session.get(ConversationRecord,UUID(conversation)).status,'completed')
        conversation,base = self.prepare()
        self.send(conversation,4,'conversation.ended')
        with patch('server.app.api.agent.LocalModel.generate',side_effect=ValueError('bad JSON')):
            self.assertEqual(self.client.post(base+'/analyze',json={}).status_code,502)
        self.assertEqual(self.session.get(ConversationRecord,UUID(conversation)).status,'failed')

    def test_four_call_limit_and_invalid_continuation_action(self):
        next_action = {'target':'patient','objective':'Verify identity with the patient','action_id':str(key('action','verify_identity'))}
        for index in range(4):
            conversation,base = self.prepare()
            self.send(conversation,4,'conversation.ended')
            with patch('server.app.api.agent.LocalModel.generate',return_value=self.output(next_action)):
                response = self.client.post(base+'/analyze',json={})
            self.assertEqual(response.json()['decision'],'continue' if index<3 else 'needs_review')
            self.metadata['parent_conversation_id'] = conversation
        del self.metadata['parent_conversation_id']
        conversation,base = self.prepare()
        self.send(conversation,4,'conversation.ended')
        with patch('server.app.api.agent.LocalModel.generate',return_value=self.output({**next_action,'action_id':str(uuid4())})):
            self.assertEqual(self.client.post(base+'/analyze',json={}).json()['decision'],'needs_review')

    def cancel_path(self, conversation):
        from server.models.context import Practice
        from server.app.services.auth import practice_info
        slug=practice_info(self.session.get(Practice,UUID(self.metadata['practice_id']))).slug
        base='/api/practices/'+slug
        self.assertEqual(self.client.post(base+'/auth/login',json={'username':'taylor.demo','password':'password'}).status_code,200)
        return base+'/conversations/'+conversation+'/cancel'

    def test_cancel_preserves_partial_turn_and_rejects_late_events(self):
        from server.models.conversation import ConversationTranscript
        conversation,base=self.prepare()
        turn=str(uuid4())
        self.send(conversation,4,'transcript.started',transcript_id=turn,turn_index=1,speaker='ai_agent')
        self.send(conversation,5,'transcript.word',transcript_id=turn,word_index=1,delta='Let me ')
        path=self.cancel_path(conversation)
        with patch('server.app.api.simulations.simulator_request',new_callable=AsyncMock) as simulator:
            simulator.return_value={'status':'cancelling'}
            response=self.client.post(path)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(self.client.post(path).status_code,200)
            simulator.assert_called_with('POST','/cancel',json={'conversation_id':conversation})
        self.assertEqual(self.send(conversation,6,'transcript.word',transcript_id=turn,word_index=2,delta='continue').status_code,409)
        row=self.session.get(ConversationTranscript,UUID(turn))
        self.assertEqual(row.transcript,'Let me ')
        self.assertIsNotNone(row.end_time)
        record=self.session.get(ConversationRecord,UUID(conversation))
        self.assertEqual(record.status,'failed')
        analysis=self.session.scalar(select(ConversationAnalysis).where(ConversationAnalysis.conversation_record_id==record.id))
        self.assertEqual(analysis.metrics['failure'],'cancelled_by_user')
        self.assertIsNone(analysis.next_action)
        self.assertEqual(self.client.post(base+'/dispatch').status_code,409)

    def test_cancel_requires_correct_tenant_origin_and_live_status(self):
        conversation,base=self.prepare()
        path=self.cancel_path(conversation)
        with patch('server.app.api.simulations.simulator_request',new_callable=AsyncMock) as simulator:
            self.assertEqual(self.client.post(path,headers={'Origin':'https://other.example'}).status_code,403)
            other='cedar-primary-care' if 'harbor-family-practice' in path else 'harbor-family-practice'
            self.client.post('/api/practices/'+other+'/auth/login',json={'username':'taylor.demo','password':'password'})
            self.assertEqual(self.client.post('/api/practices/'+other+'/conversations/'+conversation+'/cancel').status_code,404)
            self.client.cookies.clear()
            self.assertEqual(self.client.post(path).status_code,401)
            path=self.cancel_path(conversation)
            self.send(conversation,4,'conversation.ended')
            self.assertEqual(self.client.post(path).status_code,409)
            simulator.assert_not_called()

    def test_failed_record_cannot_be_resurrected_by_late_analysis(self):
        from server.app.api.agent import fail_record
        conversation,base=self.prepare()
        self.send(conversation,4,'conversation.ended')
        def finish_late(*args,**kwargs):
            fail_record(self.session,UUID(conversation),'cancelled_by_user')
            return self.output()
        with patch('server.app.api.agent.LocalModel.generate',side_effect=finish_late):
            response=self.client.post(base+'/analyze',json={})
        self.assertEqual(response.json()['decision'],'failed')
        self.assertEqual(self.session.get(ConversationRecord,UUID(conversation)).status,'failed')
