from unittest.mock import patch, AsyncMock
from uuid import UUID, uuid4
from sqlalchemy import select
from server.tests.test_ingestion import IngestionTests
from server.models.conversation import ConversationAnalysis, ConversationRecord, ActionTask
from server.models.workflow import WorkflowRun
from server.core.workflow_seed import key


class IntakeAnalysisTests(IngestionTests):
    def prepare_intake(self):
        conversation=self.create(); base='/api/conversations/'+conversation
        self.assertEqual(self.client.post(base+'/agent-context',json={}).status_code,200)
        from server.models.context import Patient
        patient=self.session.get(Patient,UUID(self.source.context['metadata']['patient_id']))
        lines=[('patient',f'I am {patient.first_name} {patient.last_name}, born {patient.date_of_birth.isoformat()}. Yes, you may discuss my prescription.'),
               ('patient','My prescription is delayed. I want to know when I can collect it.'),
               ('ai_agent','I will log this request and contact the pharmacy to check the delay.')]
        seq=0
        for index,(speaker,speech) in enumerate(lines):
            tid=str(uuid4())
            seq+=1;self.send(conversation,seq,'transcript.started',transcript_id=tid,turn_index=index,speaker=speaker)
            seq+=1;self.send(conversation,seq,'transcript.word',transcript_id=tid,word_index=1,delta=speech)
            seq+=1;self.send(conversation,seq,'transcript.completed',transcript_id=tid)
        self.send(conversation,seq+1,'conversation.ended')
        return conversation,base,lines

    def output(self, lines, route=True):
        plans=[{'kind':kind,'target':'practice','description':f'{kind} the prescription delay request','workflow_code':None,'action_code':None}
               for kind in ('log','notification','message')]
        if route: plans.append({'kind':'call','target':'pharmacy','description':'Ask the pharmacy why the prescription is delayed',
                               'workflow_code':'new_prescription','action_code':None})
        return {'summary':'The patient requested assistance with a delayed prescription. The practice plans to contact the pharmacy.',
                'overall_sentiment':'neutral','reason_for_call':'Prescription delayed','actions_needed':['Check the prescription delay'],
                'selected_workflow':'new_prescription' if route else None,'routing_reason':'Unresolved prescription fulfillment' if route else 'No follow-up workflow needed',
                'planned_actions':plans,'intake':{'verified':True,'contact_permission':True,'identity_evidence':lines[0][1],
                    'reason':'Prescription delayed','requested_outcome':'Collect the prescription','reason_evidence':lines[1][1],
                    'proposed_actions':['Log the request','Contact pharmacy'],'plan_evidence':lines[2][1]}}

    def test_after_call_evidence_updates_all_intake_steps_and_executes_saved_plan(self):
        conversation,base,lines=self.prepare_intake()
        with patch('server.app.api.agent.LocalModel.generate',return_value=self.output(lines)):
            response=self.client.post(base+'/analyze',json={})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['decision'],'continue')
        run=self.session.scalar(select(WorkflowRun).where(WorkflowRun.conversation_id==UUID(conversation)))
        self.assertEqual(run.workflow_id,key('workflow','patient_intake'))
        self.assertEqual(run.status,'intake_complete');self.assertEqual(len(run.completed_rules),3)
        analysis=self.session.scalar(select(ConversationAnalysis).where(ConversationAnalysis.conversation_record_id==UUID(conversation)))
        tasks=self.session.scalars(select(ActionTask).where(ActionTask.analysis_id==analysis.analysis_id)).all()
        self.assertEqual(len(tasks),4)
        self.assertEqual(sum(task.status=='completed' for task in tasks),3)
        self.assertTrue(all(task.result['simulated'] for task in tasks if task.status=='completed'))
        self.assertEqual(analysis.next_action['workflow_code'],'new_prescription')
        child=self.client.post('/api/conversations',json={**self.metadata,'parent_conversation_id':conversation,'start_time':self.now()})
        self.assertEqual(child.status_code,201,child.text)
        context=self.client.post('/api/conversations/'+child.json()['id']+'/agent-context',json={})
        self.assertEqual(context.json()['workflow']['workflow_id'],str(key('workflow','new_prescription')))
        self.assertEqual(next(task for task in tasks if task.kind=='call').status,'running')

    def test_rerun_recovers_failure_and_does_not_duplicate_deliveries(self):
        conversation,base,lines=self.prepare_intake()
        with patch('server.app.api.agent.LocalModel.generate',side_effect=ValueError('invalid model JSON')):
            self.assertEqual(self.client.post(base+'/analyze',json={}).status_code,502)
        with patch('server.app.api.agent.LocalModel.generate',side_effect=[ValueError('bad JSON'),self.output(lines,route=False)]) as model:
            response=self.client.post(base+'/analyze',json={'rerun':True})
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(model.call_count,2)
        self.assertEqual(response.json()['decision'],'stop')
        analysis=self.session.scalar(select(ConversationAnalysis).where(ConversationAnalysis.conversation_record_id==UUID(conversation)))
        first={task.task_id:task.result for task in self.session.scalars(select(ActionTask).where(ActionTask.analysis_id==analysis.analysis_id))}
        with patch('server.app.api.agent.LocalModel.generate',return_value=self.output(lines,route=False)):
            self.assertEqual(self.client.post(base+'/analyze',json={'rerun':True}).status_code,200)
        second={task.task_id:task.result for task in self.session.scalars(select(ActionTask).where(ActionTask.analysis_id==analysis.analysis_id))}
        self.assertEqual(first,second);self.assertEqual(len(first),3)
        self.assertNotIn('failure',analysis.metrics)
        self.assertFalse(analysis.metrics['expected_workflow_match'])

    def test_invented_identity_quote_blocks_workflow_routing(self):
        conversation,base,lines=self.prepare_intake(); output=self.output(lines)
        output['intake']['identity_evidence']='This never occurred in the conversation.'
        with patch('server.app.api.agent.LocalModel.generate',return_value=output):
            response=self.client.post(base+'/analyze',json={})
        self.assertEqual(response.json()['decision'],'needs_review')
        self.assertEqual(self.client.post(base+'/dispatch').json()['status'],'stopped')

    def test_tenant_retry_requires_auth_and_rejects_live_calls(self):
        conversation=self.create()
        self.client.post('/api/conversations/'+conversation+'/agent-context',json={})
        self.client.headers.pop('Authorization')
        endpoint=f'/api/practices/meadow-family-care/conversations/{conversation}/analyze'
        self.assertEqual(self.client.post(endpoint).status_code,401)

    def login_path(self, conversation):
        from server.models.context import Practice
        from server.app.services.auth import practice_info
        slug=practice_info(self.session.get(Practice,UUID(self.metadata['practice_id']))).slug
        base='/api/practices/'+slug
        self.assertEqual(self.client.post(base+'/auth/login',json={'username':'taylor.demo','password':'password'}).status_code,200)
        return base+'/conversations/'+conversation+'/analyze'

    def test_tenant_retry_runs_saved_plan_and_enforces_origin_and_scope(self):
        conversation,base,lines=self.prepare_intake()
        path=self.login_path(conversation)
        self.assertEqual(self.client.post(path,headers={'Origin':'https://other.example'}).status_code,403)
        with patch('server.app.api.agent.LocalModel.generate',return_value=self.output(lines)), patch('server.app.api.agent.simulator_request',new_callable=AsyncMock) as simulator:
            simulator.return_value={'status':'accepted'}
            response=self.client.post(path)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['dispatch']['status'],'accepted')
            simulator.assert_called_once()
        other='cedar-primary-care' if 'harbor-family-practice' in path else 'harbor-family-practice'
        self.client.post('/api/practices/'+other+'/auth/login',json={'username':'taylor.demo','password':'password'})
        self.assertEqual(self.client.post('/api/practices/'+other+'/conversations/'+conversation+'/analyze').status_code,404)

    def test_multiple_call_actions_queue_serially_and_record_child_failures(self):
        conversation,base,lines=self.prepare_intake(); output=self.output(lines)
        output['planned_actions'].append({'kind':'call','target':'provider','description':'Ask the prescriber to review the delayed prescription',
                                          'workflow_code':'new_prescription','action_code':None})
        with patch('server.app.api.agent.LocalModel.generate',return_value=output):
            self.client.post(base+'/analyze',json={})
        child=self.client.post('/api/conversations',json={**self.metadata,'parent_conversation_id':conversation,'start_time':self.now()}).json()['id']
        self.client.post('/api/conversations/'+child+'/agent-context',json={})
        tid=str(uuid4())
        self.send(child,1,'transcript.started',transcript_id=tid,turn_index=0,speaker='pharmacy')
        self.send(child,2,'transcript.word',transcript_id=tid,word_index=1,delta='The prescription is delayed. Please ask the prescriber to review it.')
        self.send(child,3,'transcript.completed',transcript_id=tid)
        self.client.post('/api/conversations/'+child+'/failed',json={})
        analysis=self.session.scalar(select(ConversationAnalysis).where(ConversationAnalysis.conversation_record_id==UUID(conversation)))
        calls=self.session.scalars(select(ActionTask).where(ActionTask.analysis_id==analysis.analysis_id,ActionTask.kind=='call')).all()
        first=next(task for task in calls if task.target=='pharmacy')
        self.assertEqual(first.status,'failed')
        self.assertEqual(first.result['conversation_id'],child)
        # Reanalyzing the child completes the call operation and picks the next
        # previously saved call instead of losing the rest of the action list.
        with patch('server.app.api.agent.LocalModel.generate',return_value={**self.output(lines,route=False),'planned_actions':[],'intake':None}):
            response=self.client.post('/api/conversations/'+child+'/analyze',json={'rerun':True})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['next_action']['target'],'provider')
        self.assertEqual(first.status,'completed')
        self.assertNotIn('failure',first.result)

    def test_missing_permission_is_not_recorded_as_refusal(self):
        from server.models.context import Patient
        conversation=self.create();base='/api/conversations/'+conversation
        self.client.post(base+'/agent-context',json={})
        patient=self.session.get(Patient,UUID(self.source.context['metadata']['patient_id']))
        speech=f'My full name is {patient.first_name} {patient.last_name}, born {patient.date_of_birth.isoformat()}.'
        tid=str(uuid4())
        self.send(conversation,1,'transcript.started',transcript_id=tid,turn_index=0,speaker='patient')
        self.send(conversation,2,'transcript.word',transcript_id=tid,word_index=1,delta=speech)
        self.send(conversation,3,'transcript.completed',transcript_id=tid)
        observation={'action_id':str(key('action','verify_identity')),'status':'completed','evidence':speech,
                     'result':{'verified':True,'contact_permission':False,'evidence':speech}}
        self.assertEqual(self.client.post(base+'/observations',json={'observations':[observation]}).status_code,422)
        run=self.session.scalar(select(WorkflowRun).where(WorkflowRun.conversation_id==UUID(conversation)))
        self.assertEqual(run.status,'active');self.assertEqual(run.completed_rules,[])

    def test_later_consent_corrects_premature_terminal_intake(self):
        conversation,base,lines=self.prepare_intake()
        run=self.session.scalar(select(WorkflowRun).where(WorkflowRun.conversation_id==UUID(conversation)))
        run.status='permission_needed';run.completed_rules=[str(key('rule','intake_identity'))]
        self.session.flush()
        with patch('server.app.api.agent.LocalModel.generate',return_value=self.output(lines)):
            response=self.client.post(base+'/analyze',json={})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(run.status,'intake_complete');self.assertEqual(len(run.completed_rules),3)
        self.assertEqual(response.json()['decision'],'continue')

    def test_turn_indices_resolve_original_evidence_instead_of_model_paraphrases(self):
        conversation,base,lines=self.prepare_intake();output=self.output(lines)
        for name,index in [('identity',0),('reason',1),('plan',2)]:
            output['intake'][name+'_turn_index']=index
            output['intake'][name+'_evidence']='A paraphrase that is not an exact quote.'
        with patch('server.app.api.agent.LocalModel.generate',return_value=output):
            response=self.client.post(base+'/analyze',json={})
        self.assertEqual(response.status_code,200,response.text)
        run=self.session.scalar(select(WorkflowRun).where(WorkflowRun.conversation_id==UUID(conversation)))
        self.assertEqual(run.status,'intake_complete')
        self.assertEqual([row['evidence'] for row in run.observations],[line[1] for line in lines])
