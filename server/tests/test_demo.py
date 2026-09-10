import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select

from server.tests import test_auth
from server.models.conversation import ConversationRecord, ConversationTranscript, ConversationAnalysis, ConversationEvent, Action
from server.models.simulation import SimulationConversation
from server.models.health import PriorAuthorization


class DemoTests(unittest.TestCase):
    setUpClass = classmethod(test_auth.AuthTests.setUpClass.__func__)
    setUp = test_auth.AuthTests.setUp
    tearDown = test_auth.AuthTests.tearDown
    login = test_auth.AuthTests.login


    def test_clear_all_practices_and_reset_flags(self):
        self.login()
        source = self.session.scalar(select(SimulationConversation))
        source.is_used = True
        self.session.flush()
        with patch('server.app.api.demo.simulator_request', new_callable=AsyncMock) as request:
            request.return_value = {'status': 'maintenance'}
            response = self.client.post(self.harbor + '/demo/clear')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(request.call_args_list[0].args, ('POST', '/maintenance/start'))
        self.assertEqual(request.call_args_list[-1].args, ('POST', '/maintenance/end'))
        for model in (ConversationRecord, ConversationTranscript, ConversationAnalysis, ConversationEvent, Action):
            self.assertEqual(self.session.scalar(select(func.count()).select_from(model)), 0)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(SimulationConversation).where(SimulationConversation.is_used)), 0)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(PriorAuthorization).where(PriorAuthorization.request_action_id.is_not(None))), 0)


    def test_auth_origin_and_busy_guard(self):
        from fastapi import HTTPException
        self.assertEqual(self.client.post(self.harbor + '/demo/clear').status_code, 401)
        self.assertEqual(self.client.post(self.harbor + '/demo/seed').status_code, 401)
        self.login()
        self.assertEqual(self.client.post(self.cedar + '/demo/clear').status_code, 403)
        self.assertEqual(self.client.post(self.harbor + '/demo/clear', headers={'Origin':'https://other.example'}).status_code, 403)
        with patch('server.app.api.demo.simulator_request', new_callable=AsyncMock) as request, patch('server.app.api.demo.clear_records') as clear:
            request.side_effect = HTTPException(409, 'Busy')
            self.assertEqual(self.client.post(self.harbor + '/demo/clear').status_code, 409)
            clear.assert_not_called()


    def test_seed_runs_script_and_releases_reservation_on_failure(self):
        self.login()
        process = AsyncMock()
        process.returncode = 1
        process.communicate.return_value = (b'', b'private details')
        with patch('server.app.api.demo.simulator_request', new_callable=AsyncMock) as request, patch('server.app.api.demo.asyncio.create_subprocess_exec', new_callable=AsyncMock) as spawn:
            spawn.return_value = process
            response = self.client.post(self.harbor + '/demo/seed')
            self.assertEqual(response.status_code, 500)
            self.assertNotIn('private details', response.text)
            self.assertTrue(str(spawn.call_args.args[1]).endswith('/seed_data.py'))
            self.assertEqual(request.call_args_list[-1].args, ('POST', '/maintenance/end'))
            process.returncode = 0
            self.assertEqual(self.client.post(self.harbor + '/demo/seed').status_code, 200)
