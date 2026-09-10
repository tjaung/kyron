import unittest
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from server.tests import test_auth
from server.core.workflow_seed import ACTIONS, RULES, key
from server.app.crud.conversations import create_conversation
from server.app.services.workflows import checklist, record_result, advance
from server.models.workflow import WorkflowRun
from server.models.simulation import SimulationConversation
from server.schemas.conversation import ConversationCreate


class WorkflowTests(unittest.TestCase):
    setUpClass = classmethod(test_auth.AuthTests.setUpClass.__func__)
    setUp = test_auth.AuthTests.setUp
    tearDown = test_auth.AuthTests.tearDown
    login = test_auth.AuthTests.login

    def make_run(self, rule='identity'):
        practice_id = self.client.get(self.harbor).json()['practice_id']
        source = self.session.scalar(select(SimulationConversation).where(SimulationConversation.transcript['metadata']['practice_id'].astext == practice_id))
        links = source.transcript['metadata']
        record = create_conversation(self.session, ConversationCreate(**{k:links[k] for k in ('practice_id','patient_practice_id','prescription_id')},
            source_conversation_id=source.conversation_id,start_time=datetime.now(timezone.utc)))
        run = WorkflowRun(workflow_id=key('workflow','new_prescription'),conversation_id=record.id,
            practice_id=record.practice_id,current_rule_id=key('rule',rule),created_at=datetime.now(timezone.utc))
        self.session.add(run); self.session.flush()
        return run

    def observe(self, run, code, result, status='completed'):
        record_result(self.session,run,key('action',code),status,result,'test receipt')

    def test_checklist_any_order_missing_and_failed_values_block(self):
        run = self.make_run('documentation')
        self.observe(run,'confirm_prescriber_support',{'status':'confirmed','evidence':'Signed statement'})
        with self.assertRaises(HTTPException): advance(self.session,run)
        self.observe(run,'collect_clinical_documentation',{'status':'ready','received_documents':['visit note']})
        self.assertIn('missing_documents',run.observations[-1]['missing_fields'])
        with self.assertRaises(HTTPException): advance(self.session,run)
        self.observe(run,'collect_clinical_documentation',{'status':'ready','received_documents':['visit note'],'missing_documents':[]},status='failed')
        with self.assertRaises(HTTPException): advance(self.session,run)
        self.observe(run,'collect_clinical_documentation',{'status':'ready','received_documents':['visit note'],'missing_documents':[]})
        self.assertTrue(all(row['ready'] for row in checklist(self.session,run)))
        advance(self.session,run)
        self.assertEqual(run.current_rule_id,key('rule','submit_pa'))
        self.assertEqual(len(run.observations),4)

    def test_negative_return_is_recorded_and_branches_without_claiming_success(self):
        run = self.make_run('decision')
        self.observe(run,'document_insurance_status',{'status':'denied','payer_reference':'P-123','decision_reason':'Formulary exclusion'})
        advance(self.session,run)
        self.assertEqual(run.current_rule_id,key('rule','denial'))
        self.observe(run,'schedule_followup',{'owner':'Practice','follow_up_at':'Tomorrow','reason':'Prescriber review'})
        self.observe(run,'route_denial_to_prescriber',{'denial_reference':'P-123','review_request_reference':'R-1','follow_up_at':'Tomorrow'})
        advance(self.session,run)
        self.assertEqual(run.status,'waiting_for_prescriber_review')

    def test_approval_does_not_imply_paid_claim_or_ready_medication(self):
        run = self.make_run('decision')
        self.observe(run,'document_insurance_status',{'status':'approved','payer_reference':'P-1','decision_reason':'Criteria met'})
        advance(self.session,run)
        self.assertEqual(run.current_rule_id,key('rule','pharmacy_notification'))
        self.observe(run,'notify_pharmacy',{'notification_reference':'N-1','payer_reference':'P-1'})
        advance(self.session,run)
        self.observe(run,'check_pharmacy_claim',{'status':'paid','reason':'none','pharmacy_reference':'C-1'})
        advance(self.session,run)
        self.assertEqual(run.current_rule_id,key('rule','fill'))
        self.observe(run,'confirm_fill_ready',{'status':'delayed','pharmacy_reference':'C-1','patient_cost':'20 USD','pickup_or_delivery':'Awaiting stock'})
        advance(self.session,run)
        self.assertEqual(run.current_rule_id,key('rule','followup'))
        self.assertEqual(run.status,'active')

    def test_unknown_action_invalid_values_and_cross_tenant_requests(self):
        run = self.make_run()
        with self.assertRaises(HTTPException): self.observe(run,'notify_pharmacy',{})
        self.observe(run,'verify_identity',{'verified':'yes','contact_permission':True,'evidence':'Call'})
        self.assertIn('verified',run.observations[-1]['invalid_fields'])
        with self.assertRaises(HTTPException): advance(self.session,run)
        base = self.harbor + '/workflow-runs/' + str(run.run_id)
        self.assertEqual(self.client.get(base).status_code,401)
        self.login()
        self.assertEqual(self.client.get(base).status_code,200)
        self.assertEqual(self.client.get(self.harbor + '/workflows/' + str(run.workflow_id)).status_code,200)
        self.login(base=self.cedar)
        self.assertEqual(self.client.get(self.cedar + '/workflow-runs/' + str(run.run_id)).status_code,404)

    def test_clear_removes_runs_but_preserves_definition_catalog(self):
        from unittest.mock import AsyncMock, patch
        from sqlalchemy import func
        from server.models.workflow import ActionDefinition, Rule, Workflow
        self.make_run()
        models = (ActionDefinition, Rule, Workflow)
        counts = [self.session.scalar(select(func.count()).select_from(model)) for model in models]
        self.login()
        with patch('server.app.api.demo.simulator_request', new_callable=AsyncMock) as request:
            request.return_value = {'status':'maintenance'}
            response = self.client.post(self.harbor + '/demo/clear')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(WorkflowRun)),0)
        self.assertEqual(counts,[self.session.scalar(select(func.count()).select_from(model)) for model in models])

    def test_graph_references_are_valid_and_all_nodes_reachable(self):
        seen = set()
        def visit(code, ancestors):
            self.assertNotIn(code,ancestors)
            if code in seen: return
            seen.add(code)
            actions,branches = RULES[code]
            self.assertTrue(actions)
            for action in actions: self.assertIn(action,ACTIONS)
            for branch in branches:
                self.assertNotEqual(bool(branch['next_rule']),bool(branch['outcome']))
                for condition in branch['all']:
                    self.assertIn(condition['action'],actions)
                    self.assertIn(condition['field'],ACTIONS[condition['action']][-1])
                if branch['next_rule']: visit(branch['next_rule'],ancestors|{code})
        visit('identity',set())
        self.assertEqual(seen,set(RULES))
