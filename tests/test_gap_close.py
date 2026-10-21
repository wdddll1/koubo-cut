import copy
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from test_server import server
from test_premiere import project
from koubo.gap_close import TimelineMap, close_jianying, close_premiere
from koubo.premiere import export_premiere
from koubo.review import compile_review_plan


def test_shared_map_preserves_short_subtitle_offset_and_overlap():
    m = TimelineMap([(100, 200), (300, 450), (320, 400)])
    assert m.ranges == [[100, 200], [300, 450]]
    assert m.point(320) == 120
    assert m.pieces(120, 160) == [(120, 160)]
    assert m.pieces(210, 240) == []
    assert [(m.point(a), m.point(a)+b-a) for a, b in m.pieces(150, 350)] == [(50, 100), (100, 150)]


def jy_fixture(tmp_path):
    folder = tmp_path/'草稿';folder.mkdir()
    def seg(id, a, b, material='source'):
        return {'id': id, 'material_id': material, 'target_timerange': {'start': a, 'duration': b-a},
                'source_timerange': {'start': a+1000, 'duration': b-a}, 'speed': 1,
                'clip': {'transform': {'x': .3}}, 'common_keyframes': []}
    doc = {'id': 'original', 'duration': 500, 'materials': {'videos': [{'id':'black','path':str(folder/'黑色底板.png')}]},
           'tracks': [{'type':'video','name':'黑色主轨道','segments':[seg('black',0,500,'black')]},
                      {'type':'video','segments':[seg('v1',100,200),seg('v2',300,450)]},
                      {'type':'text','segments':[seg('s1',120,160),seg('s2',210,240),seg('s3',320,340)]},
                      {'type':'audio','segments':[seg('audio',100,450)]}]}
    (folder/'draft_content.json').write_text(json.dumps(doc), encoding='utf-8')
    (folder/'draft_meta_info.json').write_text('{}', encoding='utf-8')
    (folder/'黑色底板.png').touch()
    return folder, doc


def ranges(track):
    return [(s['target_timerange']['start'], s['target_timerange']['duration']) for s in track['segments']]


def test_jy_saved_manual_edit_subtitles_audio_black_and_original(tmp_path):
    folder, original = jy_fixture(tmp_path)
    before = (folder/'draft_content.json').read_bytes()
    result = close_jianying(folder)
    output = Path(result['path'])
    doc = json.loads((output/'draft_content.json').read_text(encoding='utf-8'))
    assert (folder/'draft_content.json').read_bytes() == before
    assert doc['id'] != original['id'] and doc['duration'] == 250
    assert ranges(doc['tracks'][0]) == [(0,250)]
    assert ranges(doc['tracks'][1]) == [(0,100),(100,150)]
    assert ranges(doc['tracks'][2]) == [(20,40),(120,20)]
    assert ranges(doc['tracks'][3]) == [(0,100),(100,150)]
    assert [s['source_timerange']['start'] for s in doc['tracks'][3]['segments']] == [1100,1300]
    assert doc['tracks'][1]['segments'][1]['clip'] == original['tracks'][1]['segments'][1]['clip']
    assert str(output) in doc['materials']['videos'][0]['path']
    assert result['removed_duration'] == 250
    again = close_jianying(output)
    assert again['removed_duration'] == 0 and again['gap_count'] == 0


def test_jy_cross_gap_keyframes_rejected_before_copy(tmp_path):
    folder, doc = jy_fixture(tmp_path)
    doc['tracks'][3]['segments'][0]['common_keyframes'] = [{'id':'keyframe'}]
    (folder/'draft_content.json').write_text(json.dumps(doc), encoding='utf-8')
    with pytest.raises(ValueError, match='关键帧'):
        close_jianying(folder)
    assert list(tmp_path.iterdir()) == [folder]


def test_pr_actual_export_manual_delete_keeps_subtitle_offset(project, tmp_path):
    result = export_premiere(project, compile_review_plan(project), tmp_path, True, 'review')
    xml = Path(result['path'])/'timeline.xml'
    root = ET.parse(xml).getroot();seq = root.find('.//sequence')
    # Delete every video/audio span between 2 and 3 seconds. Deliberately leave
    # that span's subtitle in place, reproducing the user's manual fine edit.
    for track in seq.findall('./media/video/track')[:-1]+seq.findall('./media/audio/track'):
        for clip in list(track.findall('clipitem')):
            if clip.findtext('start') == '50' and clip.findtext('end') == '75':
                track.remove(clip)
    before = [(int(c.findtext('start')),int(c.findtext('end')))
              for c in seq.findall('./media/video/track')[-1].findall('clipitem')]
    ET.ElementTree(root).write(xml, encoding='utf-8', xml_declaration=True)
    input_bytes=xml.read_bytes()
    r=close_premiere(xml,tmp_path/'合拢')
    assert xml.read_bytes()==input_bytes
    newseq=ET.parse(r['path']).getroot().find('.//sequence')
    after=[(int(c.findtext('start')),int(c.findtext('end')))
           for c in newseq.findall('./media/video/track')[-1].findall('clipitem')]
    assert after == [(a if a<50 else a-25,b if b<=50 else b-25) for a,b in before if not (50<=a<75)]
    assert r['duration'] == 225
    assert newseq.find('./media/video/track/clipitem/end').text == '225'
    clips=newseq.findall('.//clipitem');ids={c.get('id') for c in clips}
    assert all(link.findtext('linkclipref') in ids for c in clips for link in c.findall('link'))
    for f in newseq.findall('.//file'):
        assert f.find('pathurl') is not None  # definitions on deleted clips resolved
    again=close_premiere(r['path'],tmp_path/'再次合拢')
    assert again['removed_duration']==0
    assert Path(tmp_path/'合拢'/'result.zip').is_file()


def test_xml_spanning_audio_is_split_not_stretched(tmp_path):
    root=ET.fromstring('''<xmeml><sequence><name>test</name><duration>500</duration><rate><timebase>25</timebase></rate><media>
    <video><track><clipitem id="v1"><start>100</start><end>200</end><in>0</in><out>100</out><file id="source"><pathurl>file://localhost/C:/video.mp4</pathurl></file></clipitem>
    <clipitem id="v2"><start>300</start><end>450</end><in>200</in><out>350</out><file id="source"/></clipitem></track></video>
    <audio><track><clipitem id="a"><start>100</start><end>450</end><in>50</in><out>400</out><file id="source"/></clipitem></track></audio>
    </media></sequence></xmeml>''')
    xml=tmp_path/'test.xml';ET.ElementTree(root).write(xml)
    result=close_premiere(xml,tmp_path/'out')
    clips=ET.parse(result['path']).findall('.//audio/track/clipitem')
    assert [(c.findtext('start'),c.findtext('end'),c.findtext('in'),c.findtext('out')) for c in clips] == [('0','100','50','150'),('100','250','250','400')]
    assert len({c.get('id') for c in clips}) == 2


def test_api_gap_close_and_download_report_no_project_required(server, tmp_path):
    _, client=server
    folder, _=jy_fixture(tmp_path)
    csrf=client.get('/api/state').json()['csrf_token']
    response=client.post('/api/gap-close',json={'path':str(folder)},headers={'X-Koubo-Token':csrf})
    assert response.status_code==200, response.text
    assert client.get(response.json()['report']).json()['duration']==250
    assert client.get('/gap-close/../../settings.json').status_code!=200
    assert client.post('/api/gap-close',json={'path':str(folder)}).status_code==400


@pytest.mark.parametrize('content', ['<xmeml><sequence><media/><sequence><media/></sequence></sequence></xmeml>',
                                   '<!DOCTYPE xmeml [<!ENTITY x "test">]><xmeml/>'])
def test_unsupported_xml_rejected(tmp_path, content):
    xml=tmp_path/'bad.xml';xml.write_text(content,encoding='utf-8')
    with pytest.raises(ValueError):
        close_premiere(xml,tmp_path/'out')
    assert not (tmp_path/'out').exists()
