import json
import zipfile
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import httpx
import pytest
from test_server import server

from koubo.ai import summarize
from koubo.core import make_candidate
from koubo.premiere import export_premiere, frame_plan, rate_info
from koubo.review import compile_review_plan
from koubo.workflow import compact_plan


@pytest.fixture
def project(tmp_path,monkeypatch):
    source=tmp_path/'中文 & 原片.mp4';source.touch()
    monkeypatch.setattr('koubo.premiere.MediaInfo.parse',lambda _:SimpleNamespace(audio_tracks=[SimpleNamespace(channel_s=2,sampling_rate=48000)]))
    return {'id':'1234567890abcdef','source_id':'test','source_path':str(source),'edits_version':0,
        'media':{'name':source.name,'width':640,'height':360,'fps':25,'duration':10000,'bytes':0},
        'transcript':{'tokens':[{'id':f't{i}','text':'文字','speaker':'A' if i<5 else 'B','start':i*1000+100,'end':i*1000+800} for i in range(10)]},
        'workflow':{'draft_name':'PR <测试> / 工程'},'silences':[[6000,7000]],
        'candidates':[make_candidate('ai',2000,3000,'多余例子')]}


@pytest.mark.parametrize('mode',['review','compact'])
def test_xml_frames_links_tracks_and_bundle(project,tmp_path,mode):
    project['workflow']['direct_delete']=mode=='compact'
    plan=compile_review_plan(project) if mode=='review' else compact_plan(project)
    result=export_premiere(project,plan,tmp_path,True,mode)
    target=__import__('pathlib').Path(result['path'])
    root=ET.parse(target/'timeline.xml').getroot()
    assert root.tag=='xmeml' and root.attrib['version']=='5'
    seq=root.find('./project/children/sequence')
    assert len(seq.findall('./media/video/track'))==(5 if mode=='review' else 2)
    assert len(seq.findall('./media/audio/track'))==(6 if mode=='review' else 2)
    clips=seq.findall('.//clipitem');ids={c.attrib['id'] for c in clips}
    assert len(ids)==len(clips)
    for c in clips:
        assert int(c.findtext('end'))-int(c.findtext('start'))==int(c.findtext('out'))-int(c.findtext('in'))
        assert all(link.findtext('linkclipref') in ids for link in c.findall('link'))
    frame_map=json.loads((target/'frame_map.json').read_text(encoding='utf-8'))
    if mode=='compact':
        assert frame_map['duration_frames']==225
        rows=frame_map['clips']
        assert rows[0]['timeline_in']==0
        assert all(a['timeline_out']==b['timeline_in'] for a,b in zip(rows,rows[1:]))
        assert 'B' in rows[-1]['speakers']
    assert '%20' in root.find('.//file[@id="source-file"]/pathurl').text
    with zipfile.ZipFile(tmp_path/'premiere.zip') as z:
        assert {'timeline.xml','subtitles.srt','edit_plan.json','frame_map.json','PR导入说明.txt'}<=set(z.namelist())
        assert ('black.png' in z.namelist())==(mode=='review')
        assert not any(n.endswith('.mp4') for n in z.namelist())
        assert any(n.startswith('subtitle-images/') and n.endswith('.png') for n in z.namelist())
    caption_clips=seq.findall('./media/video/track')[-1].findall('clipitem')
    assert len(caption_clips)==result['subtitle_clips']>0
    for clip in caption_clips:
        assert 0<=int(clip.findtext('start'))<int(clip.findtext('end'))<=frame_map['duration_frames']
        assert clip.findtext('./file/media/video/samplecharacteristics/alphatype')=='straight'


def test_no_subtitle_track_when_disabled(project,tmp_path):
    from pathlib import Path
    result=export_premiere(project,compile_review_plan(project),tmp_path,False,'review')
    target=Path(result['path']);root=ET.parse(target/'timeline.xml').getroot()
    assert len(root.findall('./project/children/sequence/media/video/track'))==4
    assert result['subtitle_clips']==0
    assert not (target/'subtitles.srt').exists()
    assert not (target/'subtitle-images').exists()


def test_ntsc_rate_and_cumulative_frame_mapping(project):
    project['media']['fps']=30000/1001
    project['candidates'][0]['accepted']=True
    rows,mapped,rate,_=frame_plan(project,compact_plan(project),'compact')
    assert rate[1:]==(30,True)
    assert all(a['timeline_out']==b['timeline_in'] for a,b in zip(rows,rows[1:]))
    assert abs(mapped['output_duration']-9000)<40


def test_vfr_is_rejected(project,tmp_path):
    project['media']['frame_rate_mode']='VFR'
    with pytest.raises(ValueError,match='可变帧率'):export_premiere(project,compile_review_plan(project),tmp_path)


def test_summary_stateless_separate_task_and_strict_validation():
    def handler(request):
        body=json.loads(request.content)
        assert len(body['messages'])==2
        assert '主题分析工具' in body['messages'][0]['content']
        assert json.loads(body['messages'][1]['content'])=={'document':'原文'}
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'title':'建议标题测试','topic':'主题','concise':'精简主体','key_points':['要点']})}}]})
    settings={'provider':'deepseek','model':'test','api_key':'fake'}
    assert '精简主体' in summarize('原文',settings,httpx.MockTransport(handler))['text']
    for text in ('','x'*20001,None):
        with pytest.raises(ValueError):summarize(text,settings,httpx.MockTransport(handler))


def test_malformed_summary_does_not_become_edit_plan():
    def handler(request):
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"deletions":[]}'}}]})
    with pytest.raises(ValueError,match='主题分析格式'):
        summarize('文稿',{'provider':'deepseek','model':'test','api_key':'fake'},httpx.MockTransport(handler))


def test_two_workspaces_are_isolated_and_ae_is_placeholder(server,project):
    service,client=server
    csrf=client.get('/api/state').json()['csrf_token'];headers={'X-Koubo-Token':csrf}
    service.project_dir(project['id']).mkdir();service.persist(project)
    state=client.get('/api/state?workspace=pr').json()
    assert state['workspace']=='pr' and state['projects']==[]
    assert client.get(f'/api/projects/{project["id"]}?workspace=pr').status_code==400
    assert client.get('/api/state?workspace=ae').status_code==400
    assert client.get('/?workspace=ae').status_code==200
    assert client.get('/api/state?workspace=pr&workspace=jianying').status_code==400
    assert client.post('/api/settings?workspace=pr',headers=headers,json={'api_key':'local-test-secret'}).status_code==200
    assert client.get('/api/state').json()['settings']['has_api_key'] is True
    assert 'local-test-secret' not in (service.directory/'settings.json').read_text()


def test_summary_job_needs_consent_and_result_is_one_shot(server,monkeypatch):
    import time
    service,client=server
    monkeypatch.setattr('koubo.service.ai.summarize',lambda text,settings:{'text':'主题反馈'})
    csrf=client.get('/api/state').json()['csrf_token']
    headers={'X-Koubo-Token':csrf}
    response=client.post('/api/jobs',headers=headers,json={'action':'summarize','options':{'consent':True,'text':'文稿'}})
    assert response.status_code==200
    key=response.json()['job_id']
    for _ in range(100):
        job=client.get('/api/jobs/'+key).json()
        if job.get('status')=='done':break
        time.sleep(.01)
    assert job['result']['text']=='主题反馈'
    assert key not in service.jobs
    assert client.get('/api/jobs/'+key).status_code==400
    assert not list(service.directory.rglob('*summary*'))
    with pytest.raises(ValueError,match='确认'):
        service.execute('summarize',None,{'text':'文稿'},service.settings,lambda *a:None)
