import copy
import json
import httpx
import pytest
from koubo import editorial
from koubo.ai import summarize
from koubo.core import compile_plan, make_candidate, subtitle_cues
from koubo.review import compile_review_plan, review_subtitles
from koubo.service import Service
from koubo.speakers import annotated_text
from koubo.workflow import compact_plan

SETTINGS={'provider':'deepseek','model':'mock','api_key':'mock-only'}
@pytest.fixture
def project():
    return {'id':'abcdef0123456789','source_id':'hash','source_path':'sample.mp4','edits_version':0,
        'editing_policy':'sentences','media':{'duration':12000,'fps':25},'silences':[[2500,3400]],'candidates':[],
        'transcript':{'tokens':[{'id':f't{i}','text':'嗯' if i==5 else '字','speaker':'A','start':i*400,'end':i*400+280} for i in range(30)]}}

def polish():
    return {'corrections':[{'token_id':'t1','text':'词，'}],
        'sentences':[{'from_token':'t0','to_token':'t19'},{'from_token':'t20','to_token':'t29'}],
        'fillers':[{'from_token':'t5','to_token':'t5','reason':'无语义犹豫'}]}

def apply(project,data):
    out=editorial.validate_polish(data,project)
    project['editorial']=out;project['candidates']=out['fillers']
    project['subtitle_breaks']=[s['to_token'] for s in out['sentences']]
    for t in project['transcript']['tokens']:
        if t['id'] in out['corrections']:t['corrected_text']=out['corrections'][t['id']]
    return out

def test_long_sentence_not_split_by_word_limit_pause_or_unknown(project):
    project['transcript']['tokens'][10]['speaker']='unknown'
    data=polish();data['fillers']=[];apply(project,data)
    assert len(subtitle_cues(project,compile_plan(project)))==2
    review=compile_review_plan(project)
    assert [(s['start'],s['end']) for s in review['segments']]==[(0,8000),(8000,12000)]
    assert len(review_subtitles(project,review))==2

def test_filler_moves_only_to_empty_lane_and_raw_tokens_stay(project):
    original=copy.deepcopy(project['transcript']['tokens']);apply(project,polish())
    review=compile_review_plan(project)
    assert [(s['start'],s['end']) for s in review['segments'] if s['category']=='no_dialogue']==[(2000,2280)]
    assert not any(s['category']=='delete' for s in review['segments'])
    project['workflow']={'direct_delete':True}
    assert compact_plan(project)['output_duration']==12000
    assert [t['text'] for t in project['transcript']['tokens']]==[t['text'] for t in original]
    assert '词，' in annotated_text(project)
    assert editorial.valid(project)
    project['transcript']['tokens'][0]['speaker']='B';assert not editorial.valid(project)

@pytest.mark.parametrize('value',['词。','词？','词：','词！','词；','词…','词\n'])
def test_only_requested_punctuation(project,value):
    data=polish();data['corrections'][0]['text']=value
    with pytest.raises(ValueError):editorial.validate_polish(data,project)

@pytest.mark.parametrize('mutate',[
    lambda d:d['sentences'][0].update(from_token='t1'),
    lambda d:d['sentences'][1].update(from_token='t19'),
    lambda d:d['fillers'][0].update(from_token='t4'),
    lambda d:d['sentences'][0].update(to_token='missing')])
def test_invalid_ranges_do_not_apply(project,mutate):
    original=copy.deepcopy(project);data=polish();mutate(data)
    with pytest.raises(ValueError):editorial.validate_polish(data,project)
    assert project==original

def test_cannot_merge_two_people(project):
    project['transcript']['tokens'][10]['speaker']='B'
    with pytest.raises(ValueError):editorial.validate_polish(polish(),project)

def test_compression_sends_every_sentence_not_candidates(project):
    project['workflow']={'compression_enabled':True,'retention':40}
    project['candidates']=[make_candidate('ai',0,280,'旧建议')]
    requests=[]
    def respond(request):
        body=json.loads(request.content);requests.append(body)
        data=polish() if len(requests)==1 else {'deletions':[{'sentence_id':'s0002','reason':'次要例子'}]}
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(data)}}]})
    original=copy.deepcopy(project)
    result=editorial.analyze(project,SETTINGS,lambda *a:None,httpx.MockTransport(respond))
    assert project==original
    first=json.loads(requests[0]['messages'][1]['content'])
    assert all({'id','start','end','speaker','text'}<=set(t) for t in first['tokens'])
    payload=json.loads(requests[1]['messages'][1]['content'])
    assert payload['scope']=='entire_video' and len(payload['sentences'])==2
    assert payload['sentences'][0]['from_token']=='t0' and payload['sentences'][-1]['to_token']=='t29'
    deletion=[c for c in result['candidates'] if c['kind']=='ai'][0]
    assert (deletion['start'],deletion['end'])==(8000,12000)
    assert all(len(r['messages'])==2 for r in requests)

def test_hundred_percent_one_request_and_no_deletions(project):
    project['workflow']={'compression_enabled':True,'retention':100};calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(polish())}}]})
    result=editorial.analyze(project,SETTINGS,lambda *a:None,httpx.MockTransport(respond))
    assert len(calls)==1 and all(c['kind']=='filler' for c in result['candidates'])

def test_service_failed_second_stage_leaves_project_unchanged(project,tmp_path,monkeypatch):
    src=tmp_path/'source.mp4';src.write_bytes(b'fixture');project['source_path']=str(src);project['media']['bytes']=7
    service=Service(tmp_path/'data');service.project_dir(project['id']).mkdir(parents=True);service.persist(project)
    original=service.load(project['id'])
    calls=[]
    def respond(*a,**kw):
        calls.append(a)
        if len(calls)==1:return polish()
        raise ValueError('第二阶段失败')
    original.update(workflow={'compression_enabled':True,'retention':50},diarization={'status':'done'},review_confirmed=True);service.persist(original)
    monkeypatch.setattr('koubo.ai.request_suggestions',respond)
    with pytest.raises(ValueError):service.execute('analyze',project['id'],{'consent':True},SETTINGS,lambda *a:None)
    assert service.load(project['id'])==original and len(calls)==2

def test_migration_discards_only_unconfirmed_automatic_fragments(project,tmp_path):
    project.pop('editing_policy');project['candidates']=[make_candidate('repeat',100,200,'旧自动'),make_candidate('manual',300,500,'人工'),make_candidate('ai',800,1000,'已确认',accepted=True)]
    service=Service(tmp_path/'data');service.project_dir(project['id']).mkdir(parents=True);service.persist(project);loaded=service.load(project['id'])
    assert loaded['editing_policy']=='sentences' and len(loaded['candidates'])==2

def test_summary_generates_title_and_rejects_missing_title():
    def transport(data):
        return httpx.MockTransport(lambda request:httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(data)}}]}))
    data={'title':'完整句子让剪辑更自然','topic':'剪辑','concise':'按完整句子剪辑','key_points':['完整句子']}
    assert summarize('原稿',SETTINGS,transport(data))['text'].startswith('建议标题\n完整句子让剪辑更自然')
    data.pop('title')
    with pytest.raises(ValueError):summarize('原稿',SETTINGS,transport(data))
