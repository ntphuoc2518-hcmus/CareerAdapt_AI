import uuid
from fastapi.testclient import TestClient
from backend.main import app
from backend.store import store
from sample_submissions import DA01A_LEVEL_2, DA02A_LEVEL_2, DA03A_LEVEL_2

client = TestClient(app)

def test_full_progression_live():
    headers = {'Authorization': 'Bearer token_student_1', 'Content-Type': 'application/json'}

    # 1. Reset
    resp = client.delete('/me/data', headers=headers)
    assert resp.status_code == 200

    # 2. Submit DA01A
    sub_1 = {
        'task_id': 'DA01A',
        'submission_text': DA01A_LEVEL_2,
        'mode': 'ASSESSMENT',
        'idempotency_key': f'prog-live-{uuid.uuid4()}'
    }
    resp = client.post('/submissions', json=sub_1, headers=headers)
    assert resp.status_code == 201

    resp = client.post('/roadmaps', json={}, headers=headers)
    assert resp.status_code == 200
    rd1 = resp.json()['evaluation']
    assert rd1['coverage'] == 0.5
    assert rd1['is_readiness_locked'] is True

    # 3. Submit DA02A (Python & Data Viz)
    sub_2 = {
        'task_id': 'DA02A',
        'submission_text': DA02A_LEVEL_2,
        'mode': 'ASSESSMENT',
        'idempotency_key': f'prog-live-{uuid.uuid4()}'
    }
    resp = client.post('/submissions', json=sub_2, headers=headers)
    assert resp.status_code == 201

    resp = client.post('/roadmaps', json={}, headers=headers)
    assert resp.status_code == 200
    rd2 = resp.json()['evaluation']
    assert rd2['coverage'] == 0.85
    assert rd2['is_readiness_locked'] is False
    assert rd2['readiness'] is not None

    # 4. Submit DA03A (Written Communication)
    sub_3 = {
        'task_id': 'DA03A',
        'submission_text': DA03A_LEVEL_2,
        'mode': 'ASSESSMENT',
        'idempotency_key': f'prog-live-{uuid.uuid4()}'
    }
    resp = client.post('/submissions', json=sub_3, headers=headers)
    assert resp.status_code == 201

    resp = client.post('/roadmaps', json={}, headers=headers)
    assert resp.status_code == 200
    rd3 = resp.json()['evaluation']
    assert rd3['coverage'] == 1.0
    assert rd3['is_readiness_locked'] is False
    assert rd3['readiness'] == 100.0

if __name__ == '__main__':
    test_full_progression_live()
    print("ALL LIVE PROGRESSION TESTS PASSED!")
