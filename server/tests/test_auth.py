from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.app.main import app
from server.app.crud.conversations import events_after
from server.app.services.auth import COOKIE_NAME
from server.core.config import settings
from server.core.database import engine, get_session
from server.core.seed import initialize_database
from server.models.context import Practice, Provider, ProviderPractice
from server.models.simulation import SimulationConversation


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()

    def setUp(self):
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.session = Session(bind=self.connection)
        app.dependency_overrides[get_session] = lambda: self.session
        self.client = TestClient(app)
        self.harbor = "/api/practices/harbor-family-practice"
        self.cedar = "/api/practices/cedar-primary-care"

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def login(self, base=None, username="taylor.demo", password="password"):
        return self.client.post((base or self.harbor) + "/auth/login",
                                json={"username": username, "password": password})

    def test_login_cookie_restore_and_logout(self):
        self.assertEqual(len(self.client.get('/api/practices').json()), 2)
        self.assertEqual(self.client.get(self.harbor + '/auth/me').status_code, 401)
        login = self.login()
        self.assertEqual(login.status_code, 200, login.text)
        cookie = login.headers['set-cookie']
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=lax', cookie)
        self.assertIn('Max-Age=28800', cookie)
        self.assertNotIn('token', login.json())
        self.assertEqual(self.client.get(self.harbor + '/auth/me').json()['provider']['username'], 'taylor.demo')
        logout = self.client.post(self.harbor + '/auth/logout')
        self.assertEqual(logout.status_code, 204)
        self.assertIn('Max-Age=0', logout.headers['set-cookie'])
        self.assertEqual(self.client.get(self.harbor + '/auth/me').status_code, 401)

    def test_invalid_credentials_and_provider_membership(self):
        self.assertEqual(self.login(password='wrong').status_code, 401)
        self.assertEqual(self.login(username='unknown.person').status_code, 401)
        harbor = self.session.scalar(select(Practice).where(Practice.name == 'Harbor Family Practice'))
        provider = Provider(provider_id=uuid4(), first_name='Only', last_name='Harbor')
        self.session.add(provider)
        self.session.flush()
        self.session.add(ProviderPractice(provider_practice_id=uuid4(), provider_id=provider.provider_id,
                                         practice_id=harbor.practice_id))
        self.session.flush()
        self.assertEqual(self.login(username='only.harbor').status_code, 200)
        self.assertEqual(self.login(base=self.cedar, username='only.harbor').status_code, 401)

    def test_cookie_cannot_cross_practice_urls_or_records(self):
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.client.get(self.cedar + '/auth/me').status_code, 403)
        self.assertEqual(self.client.get(self.cedar + '/simulations').status_code, 403)
        self.assertEqual(self.client.get(self.cedar + '/events').status_code, 403)
        listed = self.client.get(self.harbor + '/simulations')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 3)
        practice_id = self.client.get(self.harbor).json()['practice_id']
        for row in listed.json():
            source = self.session.get(SimulationConversation, row['conversation_id'])
            self.assertEqual(source.transcript['metadata']['practice_id'], practice_id)
        other = self.session.scalar(select(SimulationConversation).where(
            SimulationConversation.transcript['metadata']['practice_id'].astext != practice_id))
        self.assertEqual(self.client.post(self.harbor + f'/simulations/{other.conversation_id}/run').status_code, 404)
        with patch('server.app.api.simulations.simulator_request', new_callable=AsyncMock) as call:
            call.return_value = {'status': 'running', 'name': 'private name',
                                 'source_conversation_id': str(other.conversation_id)}
            state = self.client.get(self.harbor + '/simulations/status').json()
            self.assertEqual(state, {'status': 'busy'})

    def test_tampered_and_expired_tokens_are_rejected(self):
        self.login()
        valid = self.client.cookies.get(COOKIE_NAME)
        self.client.cookies.clear()
        self.client.cookies.set(COOKIE_NAME, valid[:-8] + 'tampered')
        self.assertEqual(self.client.get(self.harbor + '/auth/me').status_code, 401)
        claims = jwt.decode(valid, settings.jwt_secret, algorithms=['HS256'], audience='kyron-client')
        claims['exp'] = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.client.cookies.clear()
        self.client.cookies.set(COOKIE_NAME, jwt.encode(claims, settings.jwt_secret, algorithm='HS256'))
        self.assertEqual(self.client.get(self.harbor + '/auth/me').status_code, 401)
        self.assertEqual(self.client.post(self.harbor + '/auth/logout').status_code, 204)

    def test_anonymous_ingestion_and_foreign_origin_are_rejected(self):
        self.assertEqual(self.client.post('/api/conversations', json={}).status_code, 401)
        response = self.client.post(self.harbor + '/auth/login',
            json={'username': 'taylor.demo', 'password': 'password'}, headers={'Origin': 'https://other.example'})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('set-cookie', response.headers)

    def test_event_query_is_filtered_to_the_authenticated_practice(self):
        from server.app.crud.conversations import create_conversation
        from server.schemas.conversation import ConversationCreate
        practice_ids = []
        for practice in self.session.scalars(select(Practice)):
            source = self.session.scalar(select(SimulationConversation).where(
                SimulationConversation.transcript['metadata']['practice_id'].astext == str(practice.practice_id)))
            metadata = {key: source.transcript['metadata'][key]
                        for key in ('practice_id', 'patient_practice_id', 'prescription_id')}
            create_conversation(self.session, ConversationCreate(**metadata,
                source_conversation_id=source.conversation_id, start_time=datetime.now(timezone.utc)))
            practice_ids.append(practice.practice_id)
        self.session.flush()
        for practice_id in practice_ids:
            rows = events_after(self.session, 0, practice_id)
            created = [row['data'] for row in rows if row['data']['type'] == 'conversation.created']
            self.assertTrue(created)
            self.assertTrue(all(row['metadata']['practice_id'] == str(practice_id) for row in created))


if __name__ == '__main__':
    unittest.main()
