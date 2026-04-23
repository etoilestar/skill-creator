import json


def test_list_model_configs_empty(client, db):
    response = client.get('/api/model-configs/')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['data'] == []


def test_create_model_config(client, db):
    payload = {
        'name': 'test-gpt4',
        'provider': 'openai',
        'model_id': 'gpt-4o',
        'api_key_env': 'OPENAI_API_KEY',
        'max_tokens': 4096,
        'temperature': 0.7,
    }
    response = client.post(
        '/api/model-configs/',
        data=json.dumps(payload),
        content_type='application/json',
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data['success'] is True
    assert data['data']['name'] == 'test-gpt4'
    assert data['data']['provider'] == 'openai'


def test_get_model_config(client, db):
    payload = {
        'name': 'test-claude',
        'provider': 'anthropic',
        'model_id': 'claude-3-5-sonnet',
        'api_key_env': 'ANTHROPIC_API_KEY',
    }
    create_resp = client.post(
        '/api/model-configs/',
        data=json.dumps(payload),
        content_type='application/json',
    )
    config_id = create_resp.get_json()['data']['id']

    response = client.get(f'/api/model-configs/{config_id}')
    assert response.status_code == 200
    data = response.get_json()
    assert data['data']['id'] == config_id


def test_get_model_config_not_found(client, db):
    response = client.get('/api/model-configs/nonexistent-id')
    assert response.status_code == 404
