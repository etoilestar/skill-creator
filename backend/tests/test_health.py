def test_health_check(client):
    response = client.get('/api/health/')
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True
    assert data['data']['status'] == 'ok'
    assert 'timestamp' in data['data']
