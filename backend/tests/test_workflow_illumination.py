import pytest

from tests.test_api import client, register_headers, upload_image
from tests.ocr_fakes import wait_for_job


def ready_workflow(test_client, headers):
    file_id = upload_image(test_client, headers)
    flow = test_client.post('/api/v1/terminal-workflows', headers=headers, json={'file_id': file_id}).json()['data']
    base = f"/api/v1/terminal-workflows/{flow['id']}"
    changes = [
        {'regions': [{'id': 'roi-1', 'bbox': [100, 100, 500, 500]}]},
        {'side': 'right'},
        {'points': [{'id': 'p1', 'x': 80, 'y': 200, 'source': 'manual'}]},
        {'start_point_id': 'p1'},
        {'ordering': {'start': 1, 'naming': 'auto'}},
    ]
    for step, change in enumerate(changes, 1):
        response = test_client.post(f'{base}/configuration', headers=headers, json={'base_revision': flow['revision'], 'changes': change})
        assert response.status_code == 200, response.text
        flow = response.json()['data']
        response = test_client.post(f'{base}/confirmations', headers=headers, json={'base_revision': flow['revision'], 'step': step})
        assert response.status_code == 200, response.text
        flow = response.json()['data']
    return base, flow


@pytest.mark.parametrize('mode', ['none', 'he', 'clahe'])
def test_workflow_persists_and_executes_selected_illumination(tmp_path, mode):
    with client(tmp_path) as test_client:
        headers = register_headers(test_client)
        base, flow = ready_workflow(test_client, headers)
        seen = []
        core = test_client.app.state.service
        original = core.ocr_adapter.recognize_image

        def recognize(image, regions=None, *, options=None):
            seen.append(options['illumination'])
            return original(image, regions, options=options)

        core.ocr_adapter.recognize_image = recognize
        response = test_client.post(f'{base}/configuration', headers=headers, json={'base_revision': flow['revision'], 'changes': {'illumination': mode}})
        assert response.status_code == 200, response.text
        saved = test_client.get(base, headers=headers).json()['data']
        assert saved['illumination'] == mode
        assert saved['confirmed'] == 5
        for key in ('points', 'regions', 'ordering', 'start_point_id'):
            assert saved[key] == flow[key]
        response = test_client.post(f'{base}/recognitions', headers=headers, json={'base_revision': saved['revision']})
        assert response.status_code == 200, response.text
        job_id = response.json()['data']['id']
        job = wait_for_job(test_client, job_id, headers)
        assert job['status'] == 'succeeded'
        assert job['options']['illumination'] == mode
        assert seen == [mode]
        assert core.store.get('terminal_workflow_snapshot', job_id)['illumination'] == mode
        submitted = test_client.get(base, headers=headers).json()['data']
        response = test_client.post(f'{base}/configuration', headers=headers, json={'base_revision': submitted['revision'], 'changes': {'illumination': 'he'}})
        assert response.status_code == 409


def test_legacy_workflow_defaults_to_he_and_validates_updates(tmp_path):
    with client(tmp_path) as test_client:
        headers = register_headers(test_client)
        base, flow = ready_workflow(test_client, headers)
        assert flow['illumination'] == 'none'
        core = test_client.app.state.service
        flow.pop('illumination')
        core.store.put('terminal_workflow', flow['id'], flow)
        assert test_client.get(base, headers=headers).json()['data']['illumination'] == 'none'
        for invalid in ('invalid', '', None, [], {}):
            response = test_client.post(f'{base}/configuration', headers=headers, json={'base_revision': flow['revision'], 'changes': {'illumination': invalid}})
            assert response.status_code == 422
        assert test_client.get(base, headers=headers).json()['data']['revision'] == flow['revision']
        response = test_client.post(f'{base}/configuration', headers=headers, json={'base_revision': flow['revision'] - 1, 'changes': {'illumination': 'none'}})
        assert response.status_code == 409
        response = test_client.post(f'{base}/recognitions', headers=headers, json={'base_revision': flow['revision']})
        assert response.status_code == 200, response.text
        job = wait_for_job(test_client, response.json()['data']['id'], headers)
        assert job['options']['illumination'] == 'none'


def test_illumination_requires_first_five_confirmations(tmp_path):
    with client(tmp_path) as test_client:
        headers = register_headers(test_client)
        file_id = upload_image(test_client, headers)
        flow = test_client.post('/api/v1/terminal-workflows', headers=headers, json={'file_id': file_id}).json()['data']
        response = test_client.post(f"/api/v1/terminal-workflows/{flow['id']}/configuration", headers=headers, json={'base_revision': flow['revision'], 'changes': {'illumination': 'clahe'}})
        assert response.status_code == 409
