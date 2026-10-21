import copy
import json

import httpx
import pytest

from koubo.ai import analyze
from koubo.core import make_candidate, subtitle_cues
from koubo.service import Service
from koubo.workflow import compact_plan, retention_report, validate_options


@pytest.fixture
def project():
    return {'editing_policy':'legacy','id':'abcdef0123456789','source_id':'hash','source_path':'video.mp4', 'edits_version':0,
            'media':{'name':'video.mp4','duration':10000,'fps':25},
            'transcript':{'tokens':[{'id':f't{i}','text':'测试','speaker':'A' if i<5 else 'B',
                                    'start':i*1000+100,'end':i*1000+800} for i in range(10)]},
            'candidates':[make_candidate('ai',2000,4000,'次要细节'),
                          make_candidate('manual',3000,4000,'保护转场',review_action='keep')],
            'silences':[[6000,7000]]}


@pytest.mark.parametrize('config', [{'retention':19},{'retention':101},{'retention':float('nan')},
    {'retention':True},{'direct_delete':'yes'},{'speakers':3},{'draft_name':'a'*81},{'session_id':'x'}])
def test_invalid_workflow_options(config):
    with pytest.raises(ValueError): validate_options(config)


def test_direct_plan_deletes_pending_ai_but_preserves_protected_and_empty(project):
    before=copy.deepcopy(project)
    project['workflow']={'direct_delete':True}
    plan=compact_plan(project)
    assert plan['resolved_delete_ranges']==[[2000,3000]]
    assert plan['output_duration']==9000
    assert plan['resolved_keep_ranges'][1]['target_start']==2000
    assert any(k['start']<=6000 and k['end']>=7000 for k in plan['resolved_keep_ranges'])
    assert project['candidates']==before['candidates']
    cues=subtitle_cues(project,plan)
    assert all(0<=c['start']<c['end']<=9000 for c in cues)
    assert sum(len(c['text']) for c in cues)==18
    assert retention_report(project)['actual']==90


def test_bulk_selection_and_config_are_atomic_and_persisted(tmp_path,project):
    service=Service(tmp_path);service.project_dir(project['id']).mkdir();service.persist(project)
    view=service.update_candidates(project['id'],{'action':'select_all','accepted':True,'edits_version':0})
    assert view['candidates'][0]['accepted'] and not view['candidates'][1]['accepted']
    view=service.update_candidates(project['id'],{'action':'config','config':{'retention':40,'direct_delete':True,'draft_name':'测试'},'edits_version':1})
    assert view['plan']['output_duration']==9000
    assert Service(tmp_path).load(project['id'])['workflow']['draft_name']=='测试'
    with pytest.raises(ValueError):
        service.update_candidates(project['id'],{'action':'config','config':{'retention':0},'edits_version':2})
    assert service.load(project['id'])['workflow']['retention']==40


def test_bulk_delete_entire_video_rejected(tmp_path,project):
    project['candidates']=[make_candidate('manual',0,10000,'全部')]
    service=Service(tmp_path);service.project_dir(project['id']).mkdir();service.persist(project)
    with pytest.raises(ValueError):service.update_candidates(project['id'],{'action':'select_all','accepted':True,'edits_version':0})
    assert not service.load(project['id'])['candidates'][0]['accepted']


@pytest.mark.parametrize('target,expected',[(40,1),(100,0)])
def test_compression_is_stateless_and_target_100_cannot_remove_content(project,target,expected):
    project['workflow']={'compression_enabled':True,'retention':target}
    def respond(req):
        body=json.loads(req.content)
        assert len(body['messages'])==2
        assert [m['role'] for m in body['messages']]==['system','user']
        assert not {'previous_response_id','conversation','session_id'} & body.keys()
        payload=json.loads(body['messages'][1]['content'])
        assert payload['compression']['target_percent']==target
        assert payload['protected_token_ids']==['t3']
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({
            'deletions':[{'from_token':'t2','to_token':'t2','reason':'次要例子'}],'subtitle_breaks':['t4']})}}]})
    settings={'provider':'deepseek','model':'test','api_key':'fake'}
    for _ in range(2):
        result=analyze(project,settings,lambda *a:None,httpx.MockTransport(respond))
        assert len(result['candidates'])==expected
    assert not {'messages','history','raw_response'} & project.keys()


def test_one_click_runs_transcript_then_speakers_once(tmp_path,project,monkeypatch):
    service=Service(tmp_path);service.project_dir(project['id']).mkdir()
    source=tmp_path/'video.mp4';source.write_bytes(b'video')
    project['source_path']=str(source);project['media']['bytes']=5
    service.persist(project)
    (service.model_dir).mkdir(parents=True);(service.model_dir/'model.int8.onnx').touch()
    monkeypatch.setattr('koubo.service.speakers.ready',lambda _:True)
    calls=[];original=service.execute
    def execute(action,pid,options,settings,progress):
        if action=='prepare': return original(action,pid,options,settings,progress)
        calls.append((action,options));return {'speaker_count':2}
    monkeypatch.setattr(service,'execute',execute)
    assert service.execute('prepare',project['id'],{'speakers':2},{},lambda *a:None)['speaker_count']==2
    assert calls==[('transcribe',{}),('diarize',{'speakers':2})]
