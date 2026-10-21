import json
import threading
from pathlib import Path

import httpx
import pytest

from app import create_server
from koubo.service import Service


@pytest.fixture
def server(tmp_path):
    service = Service(tmp_path)
    httpd = create_server(service, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    with httpx.Client(base_url=f"http://127.0.0.1:{httpd.server_port}", trust_env=False) as client:
        yield service, client
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=2)


def test_local_api_rejects_cross_origin_and_missing_csrf(server):
    service, client = server
    assert client.get('/api/state').status_code == 200
    assert client.get('/api/state', headers={'Host': 'evil.example'}).status_code == 400
    assert client.get('/api/state', headers={'Origin': 'https://evil.example'}).status_code == 400
    assert client.post('/api/settings', json={}).status_code == 400


def test_key_never_saved_or_echoed(server):
    service, client = server
    token = client.get('/api/state').json()['csrf_token']
    response = client.post('/api/settings', json={'api_key': 'test-secret-not-a-real-key'}, headers={'X-Koubo-Token': token})
    assert response.status_code == 200
    assert response.json()['settings']['has_api_key'] is True
    assert 'test-secret' not in response.text
    assert 'test-secret' not in (service.directory / 'settings.json').read_text()
    assert Service(service.directory).settings['api_key'] == ''


def test_stale_edits_rejected_before_modifying(server):
    service, client = server
    project_id = '1234567890abcdef'
    directory = service.project_dir(project_id)
    directory.mkdir()
    project = {'id': project_id, 'source_id': 'abc', 'source_path': 'source.mp4',
               'media': {'name': 'test', 'duration': 10000}, 'transcript': {}, 'candidates': [], 'edits_version': 3}
    service.persist(project)
    token = client.get('/api/state').json()['csrf_token']
    response = client.post(f'/api/projects/{project_id}/edits', headers={'X-Koubo-Token': token},
                           json={'action': 'add', 'start': 1000, 'end': 2000, 'edits_version': 2})
    assert response.status_code == 400
    assert service.load(project_id)['candidates'] == []


def test_media_range_and_path_traversal(server):
    service, client = server
    project_id = '1234567890abcdef'
    directory = service.project_dir(project_id)
    directory.mkdir()
    source = service.directory / 'video.mp4'
    source.write_bytes(b'0123456789')
    service.persist({'id': project_id, 'source_path': str(source), 'media': {'name': 'test', 'duration': 10000}})
    response = client.get(f'/media/{project_id}/source', headers={'Range': 'bytes=2-5'})
    assert response.status_code == 206
    assert response.content == b'2345'
    assert response.headers['Content-Range'] == 'bytes 2-5/10'
    assert client.get(f'/media/{project_id}/source', headers={'Range': 'bytes=99-'}).status_code == 416
    assert client.get('/download/../../settings.json').status_code == 404


def test_review_classification_and_original_time_download(server):
    service,client=server
    pid='1234567890abcdef'
    service.project_dir(pid).mkdir()
    service.persist({'id':pid,'source_id':'abc','source_path':'source.mp4',
        'media':{'duration':10000,'name':'demo'},'transcript':{},'candidates':[],'edits_version':0})
    headers={'X-Koubo-Token':client.get('/api/state').json()['csrf_token']}
    response=client.post(f'/api/projects/{pid}/edits',headers=headers,json={
        'action':'add','start':2000,'end':5000,'review_action':'keep','edits_version':0})
    assert response.status_code==200
    assert response.json()['candidates'][0]['accepted'] is False
    assert response.json()['review_plan']['output_duration']==10000
    download=client.get(f'/download/{pid}/review_plan.json')
    assert download.status_code==200 and download.json()['segments'][1]['category']=='keep'


def test_manual_speaker_updates_transcript_and_invalidates_ai(server):
    service,client=server
    pid='1234567890abcdef'
    service.project_dir(pid).mkdir()
    service.persist({'id':pid,'source_id':'abc','source_path':'source.mp4',
        'media':{'duration':10000,'name':'demo'},'transcript':{'tokens':[
            {'id':'t1','text':'好','start':100,'end':500,'speaker':'A'}]},
        'candidates':[{'id':'old','kind':'ai','start':100,'end':500,'accepted':False}],
        'edits_version':0})
    headers={'X-Koubo-Token':client.get('/api/state').json()['csrf_token']}
    response=client.post(f'/api/projects/{pid}/edits',headers=headers,json={
        'action':'speaker','speaker':'B','token_ids':['t1'],'edits_version':0})
    assert response.status_code==200
    state=response.json()
    assert not state['candidates'] and state['transcript']['tokens'][0]['speaker_manual'] is True
    assert '人物 B' in client.get(f'/download/{pid}/speaker_transcript.txt').text
