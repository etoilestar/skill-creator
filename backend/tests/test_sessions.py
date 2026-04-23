import json


def test_create_session(client, db):
    config_payload = {
        'name': 'session-test-model',
        'provider': 'openai',
        'model_id': 'gpt-4o',
        'api_key_env': 'OPENAI_API_KEY',
    }
    config_resp = client.post(
        '/api/model-configs/',
        data=json.dumps(config_payload),
        content_type='application/json',
    )
    config_id = config_resp.get_json()['data']['id']

    session_payload = {'model_config_id': config_id}
    response = client.post(
        '/api/sessions/',
        data=json.dumps(session_payload),
        content_type='application/json',
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data['success'] is True
    assert data['data']['model_config_id'] == config_id
    assert data['data']['status'] == 'active'


def test_create_session_invalid_config(client, db):
    session_payload = {'model_config_id': 'nonexistent-id'}
    response = client.post(
        '/api/sessions/',
        data=json.dumps(session_payload),
        content_type='application/json',
    )
    assert response.status_code == 404


def test_get_session(client, db):
    config_payload = {
        'name': 'get-session-test-model',
        'provider': 'openai',
        'model_id': 'gpt-4o',
        'api_key_env': 'OPENAI_API_KEY',
    }
    config_resp = client.post(
        '/api/model-configs/',
        data=json.dumps(config_payload),
        content_type='application/json',
    )
    config_id = config_resp.get_json()['data']['id']

    session_resp = client.post(
        '/api/sessions/',
        data=json.dumps({'model_config_id': config_id}),
        content_type='application/json',
    )
    session_id = session_resp.get_json()['data']['id']

    response = client.get(f'/api/sessions/{session_id}')
    assert response.status_code == 200
    data = response.get_json()
    assert data['data']['id'] == session_id
