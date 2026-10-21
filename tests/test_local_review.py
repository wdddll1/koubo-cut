import copy
import json
import pytest
from koubo import editorial
from koubo.sentences import preview_breaks
from koubo.core import compile_plan,subtitle_cues
from koubo.service import Service
from test_editorial import polish,project,SETTINGS

@pytest.fixture
def service(project,tmp_path):
    project['media']['name']='sample.mp4'
    svc=Service(tmp_path/'data');svc.project_dir(project['id']).mkdir(parents=True)
    svc.persist(project);return svc

def edit(service,project,**data):
    p=service.load(project['id'])
    return service.update_candidates(project['id'],{'edits_version':p['edits_version'],**data})

def test_local_preview_never_collapses_without_ai(project):
    assert len(preview_breaks(project))>=3
    assert len(subtitle_cues(project,compile_plan(project)))>=3
    assert not project.get('editorial')

def test_preview_marks_speaker_boundaries(project):
    project['transcript']['tokens'][5]['speaker']='B'
    breaks=preview_breaks(project)
    assert 't4' in breaks and 't5' in breaks

def test_manual_split_join_persist_and_revoke_review(service,project):
    p=edit(service,project,action='sentence_boundary',token_id='t4',split=True)
    assert 't4' in p['preview_breaks'] and p['review_confirmed'] is False
    p=edit(service,project,action='sentence_boundary',token_id='t4',split=False)
    assert 't4' not in p['preview_breaks']
    assert p['preview_breaks'][0]!='t5'  # Don't move the same unwanted break by one token.
    assert 't4' in service.load(project['id'])['manual_joins']

def test_ai_must_preserve_manual_boundaries(project):
    project['manual_breaks']=['t4']
    with pytest.raises(ValueError,match='人工分句'):editorial.validate_polish(polish(),project)
    project['manual_breaks']=[];project['manual_joins']=['t19']
    with pytest.raises(ValueError,match='人工分句'):editorial.validate_polish(polish(),project)

def test_huge_single_speaker_monologue_response_rejected(project):
    project['transcript']['tokens']=[{'id':f't{i}','text':'字','speaker':'A','start':i*400,'end':i*400+280} for i in range(200)]
    with pytest.raises(ValueError,match='过长发言'):editorial.validate_polish({'corrections':[],'sentences':[{'from_token':'t0','to_token':'t199'}],'fillers':[]},project)

def test_review_gate_requires_diarization_then_human_confirmation(service,project,tmp_path,monkeypatch):
    src=tmp_path/'source.mp4';src.write_bytes(b'test')
    p=service.load(project['id']);p['source_path']=str(src);p['media']['bytes']=4;service.persist(p)
    calls=[]
    monkeypatch.setattr('koubo.service.editorial.analyze',lambda *a:calls.append(a))
    with pytest.raises(ValueError,match='人工复核'):service.execute('analyze',p['id'],{'consent':True},SETTINGS,lambda *a:None)
    assert not calls
    with pytest.raises(ValueError,match='本地说话人'):edit(service,project,action='confirm_review',confirmed=True)
    p['diarization']={'status':'done'};service.persist(p)
    p=edit(service,project,action='confirm_review',confirmed=True)
    assert p['review_confirmed']
    p=edit(service,project,action='speaker',speaker='B',token_ids=['t0'])
    assert p['review_confirmed'] is False

def test_old_combined_job_is_disabled(service,project,tmp_path):
    src=tmp_path/'source.mp4';src.touch();p=service.load(project['id']);p['source_path']=str(src);p['media']['bytes']=0;service.persist(p)
    with pytest.raises(ValueError,match='仅本地识别'):service.execute('prepare_editorial',p['id'],{'consent':True},SETTINGS,lambda *a:None)

def test_remove_restore_preserves_source_and_all_project_data(service,project,tmp_path):
    source=tmp_path/'original.mp4';source.write_bytes(b'original-video')
    p=service.load(project['id']);p['source_path']=str(source);service.persist(p)
    (service.project_dir(p['id'])/'extra.txt').write_text('cached-data')
    result=service.archive_project(p['id'])
    assert source.read_bytes()==b'original-video' and not service.project_dir(p['id']).exists()
    assert len(service.status()['projects'])==0 and len(service.status()['archived_projects'])==1
    service.archive_project(p['id'],restore=True,archive_id=result['archive_id'])
    assert service.load(p['id'])==p and (service.project_dir(p['id'])/'extra.txt').read_text()=='cached-data'
    assert len(service.status()['archived_projects'])==0

def test_busy_project_cannot_be_removed(service,project):
    service.jobs['running']={'project_id':project['id'],'status':'running'}
    with pytest.raises(ValueError,match='任务'):service.archive_project(project['id'])
    assert service.project_dir(project['id']).exists()

def test_restore_rejects_path_traversal(service,project):
    with pytest.raises(ValueError):service.archive_project(project['id'],restore=True,archive_id='../../outside')
    assert service.project_dir(project['id']).exists()

def test_workspace_removal_is_isolated(service,project,tmp_path):
    other=Service(tmp_path/'pr','pr',shared=service);other.project_dir(project['id']).mkdir(parents=True);other.persist(copy.deepcopy(project))
    service.archive_project(project['id'])
    assert other.load(project['id'])['id']==project['id']
