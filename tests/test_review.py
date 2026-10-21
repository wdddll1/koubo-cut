import copy
import json

import httpx
import pytest

from koubo.ai import analyze
from koubo.core import make_candidate, rule_candidates
from koubo.review import compile_review_plan, review_subtitles
from koubo.speakers import assign_tokens


@pytest.fixture
def conversation():
    tokens = [{'id':f't{i}', 'start':a, 'end':b, 'text':text, 'speaker':speaker}
              for i,(a,b,text,speaker) in enumerate([
                  (100,400,'你好','A'),(450,800,'你好','A'),(2000,2400,'好的','B'),
                  (2500,2800,'明白','B'),(6000,6400,'继续','A'),(6600,7000,'结束','A')])]
    return {'source_id':'abc', 'source_path':'original.mp4', 'media':{'duration':8000},
            'transcript':{'tokens':tokens}, 'silences':[[3000,5500]], 'candidates':[
                make_candidate('ai',2000,2800,'重复待审')],
            'diarization':{'status':'done','segments':[
                {'start':0,'end':1000,'speaker':'A'}, {'start':1800,'end':3000,'speaker':'B'},
                {'start':5800,'end':7400,'speaker':'A'}]}}


def test_review_partition_is_lossless_and_pending_ai_is_separated(conversation):
    plan = compile_review_plan(conversation)
    clips = plan['segments']
    assert plan['output_duration'] == 8000
    assert clips[0]['start'] == 0 and clips[-1]['end'] == 8000
    assert all(a['end'] == b['start'] for a,b in zip(clips,clips[1:]))
    assert all(c['target_start'] == c['start'] for c in clips)
    assert sum(c['end']-c['start'] for c in clips) == 8000
    assert any(c['category']=='delete' and c['start']==2000 for c in clips)
    assert any(c['category']=='no_dialogue' and c['start']<=3500<c['end'] for c in clips)


def test_protect_transition_wins_over_ai_and_no_dialogue(conversation):
    conversation['candidates'].append(make_candidate('manual',2100,6000,'转场保留',review_action='keep'))
    clips = compile_review_plan(conversation)['segments']
    assert all(c['category']=='keep' for c in clips if c['start']>=2100 and c['end']<=6000)


def test_recognized_speech_protects_against_vad_false_negative(conversation):
    conversation['diarization']['segments'] = []
    clips = compile_review_plan(conversation)['segments']
    for token in conversation['transcript']['tokens']:
        assert all(c['category']!='no_dialogue' for c in clips if c['start']<token['end'] and c['end']>token['start'])


def test_review_subtitles_split_by_clip_and_speaker(conversation):
    conversation['subtitle_breaks']=['t4']
    plan = compile_review_plan(conversation)
    lookup = {c['id']:c for c in plan['segments']}
    cues = review_subtitles(conversation,plan)
    assert cues and ''.join(c['text'] for c in cues)=='你好你好好的明白继续结束'
    for c in cues:
        clip=lookup[c['clip_id']]
        assert clip['start'] <= c['start'] < c['end'] <= clip['end']


def test_overlap_is_unknown_and_manual_label_survives():
    tokens = [{'start':0,'end':1000}, {'start':1000,'end':2000,'speaker':'B','speaker_manual':True}]
    assign_tokens(tokens,[{'start':0,'end':2000,'speaker':'A'},{'start':0,'end':800,'speaker':'B'}])
    assert tokens[0]['speaker']=='unknown'
    assert tokens[0]['speaker_status']=='overlap_or_uncertain'
    assert tokens[1]['speaker']=='B' and tokens[1]['acoustic_speaker']=='A'


def test_cross_person_repetition_is_not_rule_deletion():
    p={'media':{'duration':4000},'transcript':{'tokens':[
        {'id':f't{i}','text':text,'start':i*400,'end':i*400+200,'speaker':sp}
        for i,(text,sp) in enumerate([('你好','A'),('是的','A'),('你好','B'),('是的','B')])]}}
    assert not rule_candidates(p)


def test_ai_receives_labels_and_returns_subtitle_breaks(conversation):
    before=copy.deepcopy(conversation)
    def handler(request):
        body=json.loads(request.content)
        payload=json.loads(body['messages'][-1]['content'])
        assert payload['tokens'][0]['speaker']=='A'
        assert 'source_path' not in payload and 'segments' not in payload
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({
            'deletions':[], 'subtitle_breaks':['t1','t3','t5']})}}]})
    out=analyze(conversation,{'provider':'deepseek','model':'mock','api_key':'fake'},lambda *args:None,httpx.MockTransport(handler))
    assert out['subtitle_breaks']==['t1','t3','t5']
    assert conversation==before


def test_bad_subtitle_ids_reject_entire_analysis(conversation):
    def handler(request):
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{
            'content':'{"deletions":[],"subtitle_breaks":["missing"]}'}}]})
    with pytest.raises(ValueError,match='无效字词'):
        analyze(conversation,{'provider':'deepseek','model':'mock','api_key':'fake'},lambda *args:None,httpx.MockTransport(handler))


def test_estimated_word_tail_does_not_hide_entire_silent_transition(conversation):
    conversation.pop('diarization')
    conversation['silences']=[[2800,5500]]
    conversation['transcript']['tokens'][3]['end']=3100
    clips=compile_review_plan(conversation)['segments']
    assert any(c['category']=='no_dialogue' and c['start']<=4000<c['end'] for c in clips)


def test_speaker_change_retains_explicit_track_override(conversation):
    from koubo.service import invalidate_semantic_suggestions
    conversation['candidates'][0]['review_action']='keep'
    conversation['candidates'].append(make_candidate('ai',6000,7000,'旧建议'))
    invalidate_semantic_suggestions(conversation)
    assert len(conversation['candidates'])==1
    assert conversation['candidates'][0]['kind']=='manual'
    assert conversation['candidates'][0]['review_action']=='keep'


def test_frame_grid_prevents_subframe_video_fragments(conversation):
    conversation['media']['fps']=25
    conversation['candidates']=[make_candidate('ai',2000,2406,'test'),make_candidate('ai',2410,2800,'test')]
    clips=compile_review_plan(conversation)['segments']
    assert all(c['end']-c['start']>=40 for c in clips)
    assert sum(c['end']-c['start'] for c in clips)==8000


def test_straddling_word_is_not_duplicated_in_review_subtitles(conversation):
    conversation['candidates']=[make_candidate('ai',2200,2600,'测试')]
    cues=review_subtitles(conversation,compile_review_plan(conversation))
    assert ''.join(c['text'] for c in cues)=='你好你好好的明白继续结束'


def test_protected_transition_survives_overlapping_accepted_cut(conversation):
    from koubo.core import compile_plan
    conversation['candidates']=[make_candidate('ai',1000,6000,'删除',accepted=True),
        make_candidate('manual',3000,4000,'转场保护',review_action='keep')]
    assert compile_plan(conversation)['resolved_delete_ranges']==[[1000,3000],[4000,6000]]
