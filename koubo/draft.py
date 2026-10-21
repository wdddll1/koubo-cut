import json
import re
import time
import uuid
import struct
import zlib
from pathlib import Path

from .core import srt_text, subtitle_cues
from .review import TRACKS, review_subtitles


def black_png(path, width, height):
    def chunk(kind, data):
        return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data)&0xffffffff)
    raw = (b'\0'+b'\0\0\0'*width)*height
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', width,height,8,2,0,0,0))
                           +chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))


def export_draft(project, plan, root, include_subtitles=False, mode='compact', custom_name=''):
    import pyJianYingDraft as draft
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    # No existing project or root metadata is overwritten.
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', Path(project['media']['name']).stem)[:20].strip(' .') or '视频'
    prefix = '分轨审核' if mode == 'review' else '口播粗剪'
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(custom_name))[:80].strip(' .')
    if title.upper().split('.')[0] in {'CON','PRN','AUX','NUL', *{f'COM{i}' for i in range(1,10)}, *{f'LPT{i}' for i in range(1,10)}}:
        title = '_' + title
    title = title or f'{prefix}_{stem}'
    name = f"{title}_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    media = project["media"]
    folder = draft.DraftFolder(str(root))
    script = folder.create_draft(name, media["width"], media["height"],
                                fps=round(media["fps"]), allow_replace=False)
    draft_id = str(uuid.uuid4()).upper()
    script.content.update(id=draft_id, name=name)
    target = root / name
    material = draft.VideoMaterial(project["source_path"])
    relationships = []
    if mode == 'review':
        black = target/'黑色底板.png'
        black_png(black, media['width'], media['height'])
        script.append_track(draft.TrackSpec(draft.TrackType.video, '黑色主轨道'))
        script.add_segment(draft.VideoSegment(draft.VideoMaterial(str(black)), draft.Timerange(0, media['duration']*1000), volume=0), '黑色主轨道')
        # Draft API track order goes from background to foreground.
        for category in ('delete', 'no_dialogue', 'keep'):
            script.append_track(draft.TrackSpec(draft.TrackType.video, TRACKS[category]))
        for clip in plan['segments']:
            length = (clip['end']-clip['start'])*1000
            segment = draft.VideoSegment(material, draft.Timerange(clip['start']*1000,length),
                source_timerange=draft.Timerange(clip['start']*1000,length), speed=1.0)
            script.add_segment(segment, TRACKS[clip['category']])
            relationships.append({'clip_id': clip['id'], 'video_segment_id': segment.segment_id,
                                  'start':clip['start'], 'end':clip['end'], 'subtitle_segment_ids': []})
        cues = review_subtitles(project, plan)
    else:
        script.append_track(draft.TrackSpec(draft.TrackType.video, "口播原片"))
        for keep in plan["resolved_keep_ranges"]:
            length = (keep["end"] - keep["start"]) * 1000
            segment = draft.VideoSegment(material, draft.Timerange(keep["target_start"] * 1000, length),
                                         source_timerange=draft.Timerange(keep["start"] * 1000, length), speed=1.0)
            script.add_segment(segment, "口播原片")
        cues = subtitle_cues(project, plan)
    subtitle = target / "subtitles.srt"
    subtitle.write_text(srt_text(cues), encoding="utf-8-sig")
    if include_subtitles and subtitle.stat().st_size > 5:
        if mode == 'review':
            for category in ('delete', 'no_dialogue', 'keep'):
                selected = [c for c in cues if c['category'] == category]
                if not selected:
                    continue
                path = target/f'subtitles-{category}.srt'
                path.write_text(srt_text(selected), encoding='utf-8-sig')
                track = f'字幕 · {TRACKS[category]}'
                script.import_srt(str(path), track)
                for cue, text_segment in zip(selected, script.tracks[track].segments):
                    relation = next(r for r in relationships if r['clip_id'] == cue['clip_id'])
                    relation['subtitle_segment_ids'].append(text_segment.segment_id)
        else:
            script.import_srt(str(subtitle), "口播字幕")
    script.save()
    meta_path = target / "draft_meta_info.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.update({"draft_id": draft_id, "draft_name": name,
                 "draft_fold_path": str(target), "draft_root_path": str(root),
                 "tm_draft_create": int(time.time() * 1000000), "tm_draft_modified": int(time.time() * 1000000),
                 "tm_duration": plan["output_duration"] * 1000})
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (target / "edit_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    if mode == 'review':
        (target/'字幕与画面对应表.json').write_text(json.dumps({'native_binding': False,
            'reason':'当前草稿库未提供已验证的剪映5.9片段分组/删除联动接口，按要求跳过绑定。对应表不是剪映原生绑定。',
            'clips': relationships}, ensure_ascii=False, indent=2), encoding='utf-8')
    note = '已生成草稿文件；需在剪映 5.9 打开并试听验证。若草稿未显示，请重启剪映刷新列表。'
    if mode == 'review':
        note += ' 所有轨道默认可见有声，保持原片完整。删除建议只是分轨，未真正移除；字幕按片段切开，尚不支持删除画面时自动删除字幕。'
    return {"path": str(target), "name": name, 'mode':mode,
            "segments": len(plan['segments']) if mode == 'review' else len(plan["resolved_keep_ranges"]), "note":note}
