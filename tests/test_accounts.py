import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from backend.app import create_app
from backend.auth import token_hash
from backend.config import Settings


@pytest.fixture
def account_app(tmp_path):
    app = create_app(Settings(mode='fixture', database_url='sqlite:///' + str(tmp_path/'accounts.sqlite'),
                              media_dir=tmp_path/'media', identity_api_base='https://identity.invalid'))
    sequence = [0]
    remote_users = {}
    refresh_users = {}
    def upstream(request):
        import json
        data = json.loads(request.content) if request.content else {}
        path = request.url.path
        if path.endswith('/methods'):
            return httpx.Response(200, json={'sms': True, 'wechat': True, 'apple': True, 'one_click': True, 'voice': True})
        if path.endswith('/sms/send'):
            return httpx.Response(200, json={'retry_after': 60})
        if path.endswith('/me'):
            user = remote_users.get(request.headers.get('Authorization', '')[7:])
            return httpx.Response(200 if user else 401, json={'user_id': user, 'display_name': 'Tester', 'phone': ''})
        if path.endswith('/logout'):
            refresh_users.pop(data['refresh_token'], None)
            return httpx.Response(204)
        if path.endswith('/token/refresh'):
            user = refresh_users.pop(data['refresh_token'], None)
            if not user:
                return httpx.Response(401, json={})
        elif path.endswith('/sms/login'):
            if data['code'] != '123456':
                return httpx.Response(401, json={})
            user = 'phone-' + data['phone']
        elif path.endswith('/wechat'):
            if data['code'] != 'verified-wechat-code':
                return httpx.Response(401, json={})
            user = 'wechat-user'
        elif path.endswith('/apple'):
            if data['identity_token'] != 'verified-apple-token':
                return httpx.Response(401, json={})
            user = 'apple-user'
        else:
            return httpx.Response(404)
        sequence[0] += 1
        access, refresh = 'remote-access-'+str(sequence[0]), 'remote-refresh-'+str(sequence[0])
        remote_users[access] = user
        refresh_users[refresh] = user
        return httpx.Response(200, json={'user_id': user, 'access_token': access, 'refresh_token': refresh, 'expires_in': 7200})
    app.state.services.accounts.client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    with TestClient(app) as client:
        yield client, app
    app.state.services.store.engine.dispose()


def login(client, phone='13800138000', headers=None):
    response = client.post('/v1/auth/sms/login', json={'phone': phone, 'code': '123456'}, headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()


def bearer(session):
    return {'Authorization': 'Bearer ' + session['access_token']}


def test_only_three_methods_and_identity_inputs_are_verified(account_app):
    client, _ = account_app
    assert client.get('/v1/auth/methods').json() == {'sms': True, 'wechat': True, 'apple': True}
    assert client.post('/v1/auth/sms/send', json={'phone': '13800138000'}).json()['retry_after'] == 60
    assert client.post('/v1/auth/sms/send', json={'phone': 'not-a-phone'}).status_code == 422
    assert client.post('/v1/auth/sms/login', json={'phone': '13800138000', 'code': '000000'}).status_code == 401
    assert client.post('/v1/auth/apple', json={'identity_token': 'forged'}).status_code == 401
    assert client.post('/v1/auth/wechat', json={'code': 'forged'}).status_code == 401
    for path, body in [('apple', {'identity_token': 'verified-apple-token'}), ('wechat', {'code': 'verified-wechat-code'})]:
        a = client.post('/v1/auth/'+path, json=body).json()
        b = client.post('/v1/auth/'+path, json=body).json()
        assert a['user_id'] == b['user_id']
        assert client.get('/v1/auth/me', headers=bearer(a)).json()['verified']


def test_same_identity_multiple_devices_and_private_record_isolation(account_app):
    client, app = account_app
    a = login(client)
    second_device = login(client)
    b = login(client, '13900139000')
    assert a['user_id'] == second_device['user_id'] != b['user_id']
    headers = bearer(a)
    profile = client.patch('/v1/profile/preferences', json={'reference_stage': 'B1', 'context': '旅行'}, headers=headers)
    assert profile.status_code == 200
    assert client.get('/v1/profile', headers=bearer(second_device)).json()['preferences']['reference_stage'] == 'B1'
    assert client.get('/v1/profile', headers=bearer(b)).json()['preferences']['reference_stage'] == 'A2'
    store = app.state.services.store
    for kind, path, payload in [('AudioAsset', '/v1/media/private', {'filename': 'private'}),
                               ('NotebookEntry', '/v1/notebook/private', {'word': 'hello'})]:
        store.put(kind, 'private', a['user_id'], payload)
        assert client.get(path, headers=bearer(b)).status_code == 404
    job = client.post('/v1/course-generation-jobs', json={}, headers={**headers, 'Idempotency-Key':'private'}).json()
    assert client.get('/v1/course-generation-jobs/'+job['job_id'], headers=bearer(b)).status_code == 404
    ticket = client.post('/v1/feedback', json={'content': 'private'}, headers={**headers, 'Idempotency-Key':'feedback'}).json()
    assert client.get('/v1/feedback/'+ticket['id'], headers=bearer(b)).status_code == 404


def test_refresh_rotation_expiry_logout_and_other_device_survives(account_app):
    client, app = account_app
    a, other = login(client), login(client)
    store = app.state.services.store
    with store.transaction() as c:
        c.execute(update(store.auth_sessions).where(store.auth_sessions.c.access_hash == token_hash(a['access_token'])).values(expires_at=time.time()-1))
    assert client.get('/v1/profile', headers=bearer(a)).status_code == 401
    response = client.post('/v1/auth/token/refresh', json={'refresh_token':a['refresh_token']})
    assert response.status_code == 200
    refreshed = response.json()
    assert refreshed['user_id'] == a['user_id']
    assert refreshed['access_token'] != a['access_token']
    assert refreshed['refresh_token'] != a['refresh_token']
    assert client.post('/v1/auth/token/refresh', json={'refresh_token':a['refresh_token']}).status_code == 401
    assert client.get('/v1/profile', headers=bearer(refreshed)).status_code == 200
    assert client.post('/v1/auth/logout', json={'refresh_token':refreshed['refresh_token']}).status_code == 200
    assert client.get('/v1/profile', headers=bearer(refreshed)).status_code == 401
    assert client.post('/v1/auth/token/refresh', json={'refresh_token':refreshed['refresh_token']}).status_code == 401
    assert client.get('/v1/profile', headers=bearer(other)).status_code == 200
    with store.engine.connect() as c:
        rows = c.execute(select(store.auth_sessions)).mappings().all()
    assert all(other['access_token'] not in str(row) and other['refresh_token'] not in str(row) for row in rows)


def test_anonymous_adoption_preserves_data_and_revokes_old_bearer(account_app):
    client, app = account_app
    anonymous = client.post('/v1/users', json={'reference_stage':'B2'}).json()
    authenticated = login(client, headers={'X-Learning-Token':anonymous['access_token']})
    assert authenticated['user_id'] == anonymous['user_id']
    assert authenticated['adopted_anonymous']
    assert client.get('/v1/profile', headers=bearer(authenticated)).json()['preferences']['reference_stage'] == 'B2'
    assert client.get('/v1/profile', headers=bearer(anonymous)).status_code == 401
    other = login(client, '13900139000', headers={'X-Learning-Token':anonymous['access_token']})
    assert other['user_id'] != anonymous['user_id']
    assert not other['adopted_anonymous']
    app.state.services.settings.mode = 'provider'
    assert client.post('/v1/users', json={}).status_code == 403


def test_existing_identity_does_not_claim_another_anonymous_record(account_app):
    client, _ = account_app
    established = login(client)
    anonymous = client.post('/v1/users', json={'reference_stage':'C1'}).json()
    again = login(client, headers={'X-Learning-Token':anonymous['access_token']})
    assert again['user_id'] == established['user_id'] != anonymous['user_id']
    assert not again['adopted_anonymous']


def test_identity_outage_does_not_turn_into_auth_failure(account_app):
    client, app = account_app
    a = login(client)
    async def unavailable(request):
        raise httpx.ConnectError('offline')
    app.state.services.accounts.client = httpx.AsyncClient(transport=httpx.MockTransport(unavailable))
    assert client.post('/v1/auth/token/refresh', json={'refresh_token':a['refresh_token']}).status_code == 503
    assert client.get('/v1/profile', headers=bearer(a)).status_code == 200
    assert client.post('/v1/auth/logout', json={'refresh_token':a['refresh_token']}).status_code == 200
    assert client.get('/v1/profile', headers=bearer(a)).status_code == 401
