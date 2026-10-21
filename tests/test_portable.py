import json
import shutil
from pathlib import Path
from zipfile import ZipFile

import pytest
from koubo.service import Service
from koubo.portable import relocate


def test_portable_import_and_move(tmp_path, monkeypatch):
    original=tmp_path/'outside.mp4';original.write_bytes(b'video')
    data=tmp_path/'first'/'data';data.mkdir(parents=True)
    (data/'portable.json').write_text('{}')
    monkeypatch.setattr('koubo.service.media.inspect_video',lambda p:{'name':Path(p).name,'duration':1000,'audio_tracks':1,'fps':25})
    service=Service(data)
    p=service.import_video(original)
    assert p['source_relative'].startswith('uploads/')
    assert Path(p['source_path']).read_bytes()==original.read_bytes()
    assert original.exists()
    service.configure({'draft_root':str(data/'drafts')})
    assert json.loads((data/'settings.json').read_text())['draft_root']=='drafts'
    moved=tmp_path/'moved'/'data';shutil.copytree(data,moved)
    loaded=Service(moved).load(p['id'])
    assert Path(loaded['source_path']).is_relative_to(moved)
    assert Service(moved).settings['draft_root']==str(moved/'drafts')
    path=moved/'projects'/p['id']/'project.json'
    loaded['source_relative']='../../outside.mp4'
    path.write_text(json.dumps(loaded))
    with pytest.raises(ValueError):Service(moved).load(p['id'])


def test_relocate_export_cache(tmp_path):
    old=tmp_path/'old'/'data';new=tmp_path/'new'/'data';new.mkdir(parents=True)
    (new/'portable.json').write_text(json.dumps({'last_data_root':str(old)}))
    payload=json.dumps({'source_path':str(old/'uploads'/'v.mp4')}).encode()
    (new/'project.json').write_bytes(payload)
    with ZipFile(new/'premiere.zip','w') as archive:archive.writestr('edit_plan.json',payload)
    relocate(new)
    assert json.loads((new/'project.json').read_text())['source_path']==str(new/'uploads'/'v.mp4')
    with ZipFile(new/'premiere.zip') as archive:
        assert json.loads(archive.read('edit_plan.json'))['source_path']==str(new/'uploads'/'v.mp4')
