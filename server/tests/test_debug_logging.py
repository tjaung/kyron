import json
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from server.app.main import app
from simulator.debug_logging import JsonFormatter


class RequestDiagnosticTests(unittest.TestCase):
    def test_request_id_is_returned_and_correlates_error_log(self):
        request_id = str(uuid4())
        # No lifespan/DB initialization is needed for this unknown route.
        client = TestClient(app)
        with self.assertLogs('kyron.debug', level='INFO') as captured:
            response = client.get('/missing', headers={'X-Request-ID':request_id, 'Authorization':'Bearer secret-token'})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers['X-Request-ID'], request_id)
        events = [json.loads(JsonFormatter().format(record)) for record in captured.records]
        complete = next(event for event in events if event['event'] == 'api.request.completed')
        self.assertEqual(complete['request_id'], request_id)
        self.assertEqual(complete['status_code'], 404)
        self.assertNotIn('secret-token', json.dumps(events))
        response = client.get('/missing', headers={'X-Request-ID':'not-a-uuid'})
        self.assertNotEqual(response.headers['X-Request-ID'], request_id)
        UUID = __import__('uuid').UUID
        UUID(response.headers['X-Request-ID'])
