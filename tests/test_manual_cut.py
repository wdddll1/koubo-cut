from test_editorial import project
from koubo.sentences import preview_breaks
from koubo.core import make_candidate
from koubo.review import compile_review_plan
from koubo.workflow import compact_plan
from koubo.premiere import frame_plan

def test_manual_cut_preserves_visible_sentences_ignores_ai_and_keeps_all_source(project):
    project['workflow']={'manual_cut':True}
    project['candidates']=[make_candidate('ai',400,9000,'自动建议',accepted=True)]
    ends=preview_breaks(project)
    review=compile_review_plan(project)
    compact=compact_plan(project)
    assert len(review['segments'])==len(ends)==len(compact['resolved_keep_ranges'])
    assert all(s['category']=='keep' for s in review['segments'])
    assert compact['output_duration']==project['media']['duration']
    rows,_,_,_=frame_plan(project,compact,'compact')
    assert len(rows)==len(ends)
    assert all(a['timeline_out']==b['timeline_in'] for a,b in zip(rows,rows[1:]))

def test_manual_cut_still_obeys_human_delete_and_manual_boundaries(project):
    project['manual_breaks']=['t4']
    project['workflow']={'manual_cut':True,'direct_delete':True}
    project['candidates']=[make_candidate('manual',0,2000,'人工删除',accepted=True,review_action='delete')]
    plan=compact_plan(project)
    assert plan['output_duration']==10000
    assert plan['resolved_keep_ranges'][0]['start']==2000
    project['workflow']['manual_cut']=False
    assert len(compact_plan(project)['resolved_keep_ranges'])==1
