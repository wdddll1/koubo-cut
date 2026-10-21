"""Close holes in an edited timeline using ONE map for picture, sound and titles.

Inputs are saved Jianying 5.9 drafts or Premiere FCP7 XML exports. Originals
are never edited. Times remain integer microseconds (JY) or frames (XML).
"""
import copy
import json
import re
import shutil
import time
import uuid
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET


class TimelineMap:
    def __init__(self, intervals):
        self.ranges = []
        for a, b in sorted(intervals):
            if a < 0 or b <= a:
                raise ValueError('片段时间范围无效')
            if self.ranges and a <= self.ranges[-1][1]:
                self.ranges[-1][1] = max(b, self.ranges[-1][1])
            else:
                self.ranges.append([a, b])
        if not self.ranges:
            raise ValueError('没有找到剩余视频片段；黑色底板和字幕不会用作合拢依据')
        self.duration = sum(b-a for a, b in self.ranges)

    def point(self, t):
        cursor = 0
        for a, b in self.ranges:
            if t < a:
                return cursor
            if t <= b:
                return cursor+t-a
            cursor += b-a
        return cursor

    def pieces(self, a, b):
        return [(max(a, x), min(b, y)) for x, y in self.ranges
                if max(a, x) < min(b, y)]

    def report(self, old_duration):
        return {'original_duration': old_duration, 'duration': self.duration,
                'removed_duration': max(0, old_duration-self.duration),
                'retained_intervals': self.ranges,
                'gap_count': len(self.ranges)-1+(self.ranges[0][0]>0)+(old_duration>self.ranges[-1][1])}


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (UnicodeError, ValueError) as exc:
        raise ValueError('无法读取草稿 JSON；暂支持未加密的剪映 5.9 草稿') from exc


def black(name):
    return Path(str(name).replace('\\', '/')).name.lower() in ('black.png', '黑色底板.png')


def _rewrite_paths(value, source, target):
    if isinstance(value, dict):
        return {k: _rewrite_paths(v, source, target) for k, v in value.items()}
    if isinstance(value, list):
        return [_rewrite_paths(v, source, target) for v in value]
    if isinstance(value, str):
        for before, after in ((str(source), str(target)), (source.as_posix(), target.as_posix())):
            if value == before or value.startswith(before+'\\') or value.startswith(before+'/'):
                return after+value[len(before):]
    return value


def close_jianying(path):
    source = Path(path).resolve()
    if source.is_dir():
        source /= 'draft_content.json'
    if source.name != 'draft_content.json' or not source.is_file():
        raise ValueError('请选择手动精剪后保存的草稿文件夹，或其中的 draft_content.json')
    doc = read_json(source)
    tracks = doc.get('tracks', [])
    if not isinstance(tracks, list):
        raise ValueError('草稿轨道格式无效')
    materials = {v['id']: v for v in doc.get('materials', {}).get('videos', [])}
    def is_black(track, segment):
        return track.get('name') == '黑色主轨道' or black(materials.get(segment.get('material_id'), {}).get('path', ''))
    def bounds(segment):
        r = segment['target_timerange']
        return int(r['start']), int(r['start'])+int(r['duration'])
    intervals = []
    for track in tracks:
        if track.get('type') == 'video':
            for segment in track.get('segments', []):
                if not is_black(track, segment):
                    intervals.append(bounds(segment))
    mapping = TimelineMap(intervals)
    old_duration = int(doc.get('duration', 0))
    for track in tracks:
        changed = []
        for segment in track.get('segments', []):
            a, b = bounds(segment)
            old_duration = max(old_duration, b)
            if is_black(track, segment):
                segment['target_timerange'] = {'start': 0, 'duration': mapping.duration}
                if segment.get('source_timerange'):
                    segment['source_timerange']['duration'] = mapping.duration
                changed.append(segment)
                continue
            pieces = mapping.pieces(a, b)
            trimmed = pieces != [(a, b)]
            if trimmed and pieces:
                if segment.get('common_keyframes') or segment.get('keyframe_refs'):
                    raise ValueError('跨空隙片段含关键帧，请先将该片段在空隙边界切开后重试')
                if segment.get('speed', 1) != 1 or segment.get('reverse'):
                    raise ValueError('跨空隙片段存在变速或倒放，请先在空隙边界切开后重试')
            for i, (x, y) in enumerate(pieces):
                item = copy.deepcopy(segment)
                if i:
                    item['id'] = uuid.uuid4().hex
                item['target_timerange'] = {'start': mapping.point(x), 'duration': y-x}
                if trimmed and item.get('source_timerange'):
                    item['source_timerange']['start'] += x-a
                    item['source_timerange']['duration'] = y-x
                changed.append(item)
        track['segments'] = changed
    # Transitions and clip groups can carry separate timing. Refuse instead of
    # producing a silently corrupted project. Regular position/style is retained.
    if (doc.get('materials', {}).get('transitions') or doc.get('groups') or
            doc.get('group_container') or doc.get('materials', {}).get('drafts')):
        raise ValueError('此草稿包含转场或片段编组，请先在副本中解除后再合拢')
    new_id = str(uuid.uuid4()).upper()
    name = f'{source.parent.name}_精剪合拢_{time.strftime("%H%M%S")}_{uuid.uuid4().hex[:4]}'
    target = source.parent.parent/name
    report = {**mapping.report(old_duration), 'unit': 'microseconds', 'kind': 'jianying'}
    shutil.copytree(source.parent, target, ignore=shutil.ignore_patterns('.locked', '*.tmp', '*.lock'))
    try:
        doc = _rewrite_paths(doc, source.parent, target)
        doc.update(id=new_id, name=name, duration=mapping.duration)
        (target/'draft_content.json').write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
        # A previous save may have a backup with the original duration. Keep the
        # copied backup consistent so JY cannot recover stale timeline contents.
        if (target/'draft_content.json.bak').exists():
            shutil.copy2(target/'draft_content.json', target/'draft_content.json.bak')
        meta_path = target/'draft_meta_info.json'
        meta = _rewrite_paths(read_json(meta_path), source.parent, target) if meta_path.exists() else {}
        meta.update(draft_id=new_id, draft_name=name, draft_fold_path=str(target),
                    draft_root_path=str(target.parent), tm_duration=mapping.duration,
                    tm_draft_create=int(time.time()*1000000), tm_draft_modified=int(time.time()*1000000))
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        (target/'精剪合拢报告.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        # Leave a clearly identified incomplete COPY; never touch source assets.
        (target/'合拢未完成.txt').write_text('合拢未完成，请勿使用此副本。原草稿未修改。', encoding='utf-8')
        raise
    return {**report, 'path': str(target), 'name': name,
            'note': '已生成独立剪映草稿；在剪映首页刷新后打开“精剪合拢”副本。原草稿保留。'}


def _local_file(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'file' or parsed.netloc not in ('', 'localhost'):
        return None
    text = unquote(parsed.path)
    if re.match(r'^/[A-Za-z]:', text):
        text = text[1:]
    return Path(text)


def close_premiere(path, target):
    source = Path(path).resolve()
    if source.suffix.lower() != '.xml' or not source.is_file():
        raise ValueError('请在 PR 中选中精剪后的序列，导出 Final Cut Pro XML，然后填写该 XML 路径')
    if source.stat().st_size > 50*1024*1024:
        raise ValueError('XML 文件超过 50 MB，请只导出当前精剪序列')
    raw = source.read_bytes()
    if b'<!ENTITY' in raw.upper():
        raise ValueError('不支持包含外部实体的 XML')
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError('XML 格式无效') from exc
    sequences = [s for s in root.iter('sequence') if s.find('media') is not None]
    if root.tag != 'xmeml' or len(sequences) != 1:
        raise ValueError('仅支持单个序列的 Final Cut Pro XML；暂不支持嵌套或多序列')
    seq = sequences[0]
    if seq.findall('.//transitionitem'):
        raise ValueError('序列包含转场，请先在副本中移除转场或完成合拢后再加转场')
    definitions = {f.get('id'): copy.deepcopy(f) for f in root.iter('file') if len(f)}
    def file_of(clip):
        f = clip.find('file')
        return definitions.get(f.get('id'), f) if f is not None else None
    def role(clip):
        f = file_of(clip)
        url = f.findtext('pathurl', '') if f is not None else ''
        name = f.findtext('name', '') if f is not None else ''
        if black(unquote(url)) or black(name) or clip.findtext('name') == '黑色底板':
            return 'black'
        if 'subtitle-images/' in unquote(url).replace('\\', '/') or clip.get('id', '').startswith('subtitle-'):
            return 'subtitle'
        return 'picture'
    def bounds(clip):
        a, b = int(clip.findtext('start', '-1')), int(clip.findtext('end', '-1'))
        if a < 0 or b <= a:
            raise ValueError('片段时间无效或含转场边界，请先移除转场再合拢')
        return a, b
    intervals = []
    video_tracks = seq.findall('./media/video/track')
    for track in video_tracks:
        for clip in track.findall('clipitem'):
            if role(clip) == 'picture':
                if file_of(clip) is None:
                    raise ValueError('暂不支持嵌套、图形生成器或无源文件的视频片段')
                intervals.append(bounds(clip))
    mapping = TimelineMap(intervals)
    old_duration = int(seq.findtext('duration', '0'))
    for track in seq.findall('./media/video/track')+seq.findall('./media/audio/track'):
        for clip in list(track.findall('clipitem')):
            a, b = bounds(clip)
            old_duration = max(old_duration, b)
            is_black = track in video_tracks and role(clip) == 'black'
            pieces = [(a, b)] if is_black else mapping.pieces(a, b)
            trimmed = pieces != [(a, b)]
            if trimmed and pieces and (clip.findall('.//keyframe') or
                    int(clip.findtext('out', '0'))-int(clip.findtext('in', '0')) != b-a):
                raise ValueError('跨空隙片段含关键帧或变速，请先在空隙边界切开后重试')
            position = list(track).index(clip)
            track.remove(clip)
            for i, (x, y) in enumerate(pieces):
                item = copy.deepcopy(clip)
                if i:
                    item.set('id', (clip.get('id') or 'clip')+'-gap-'+str(i))
                    for link in list(item.findall('link')):
                        item.remove(link)
                values = {'start': 0 if is_black else mapping.point(x),
                          'end': mapping.duration if is_black else mapping.point(x)+y-x}
                if trimmed or is_black:
                    source_in = int(clip.findtext('in', '0'))+(x-a if not is_black else 0)
                    values.update({'in': source_in, 'out': source_in+(mapping.duration if is_black else y-x)})
                for tag, val in values.items():
                    el = item.find(tag)
                    if el is None:
                        el = ET.SubElement(item, tag)
                    el.text = str(val)
                f = item.find('file')
                if f is not None and f.get('id') in definitions:
                    item.remove(f)
                    item.append(copy.deepcopy(definitions[f.get('id')]))
                track.insert(position+i, item)
    indices = {}
    for media_type in ('video', 'audio'):
        for ti, track in enumerate(seq.findall(f'./media/{media_type}/track'), 1):
            for ci, clip in enumerate(track.findall('clipitem'), 1):
                indices[clip.get('id')] = (media_type, ti, ci)
    for clip in seq.findall('.//clipitem'):
        for link in list(clip.findall('link')):
            ref = link.findtext('linkclipref')
            if ref not in indices:
                clip.remove(link)
            else:
                for tag, val in zip(('mediatype', 'trackindex', 'clipindex'), indices[ref]):
                    el = link.find(tag)
                    if el is not None:
                        el.text = str(val)
    seq.find('duration').text = str(mapping.duration)
    title = seq.find('name')
    if title is not None:
        title.text = (title.text or source.stem)+'_精剪合拢'
    for marker in list(seq.findall('marker')):
        for tag in ('in', 'out'):
            el = marker.find(tag)
            if el is not None and int(el.text or '-1') >= 0:
                el.text = str(mapping.point(int(el.text)))
    target = Path(target)
    target.mkdir(parents=True, exist_ok=False)
    # Keep all generated caption pictures with the XML, including ones whose
    # defining <file> lived on a deleted clip. Source video stays referenced.
    copied = {}
    for f in seq.iter('file'):
        url = f.find('pathurl')
        if url is None:
            continue
        local = _local_file(url.text or '')
        if local and ('subtitle-images/' in local.as_posix() or black(local.name)):
            if not local.is_file():
                raise ValueError('字幕图片或黑色底板已丢失，请先恢复原工程包素材')
            key = str(local.resolve())
            if key not in copied:
                caption = 'subtitle-images/' in local.as_posix()
                dest = target/('subtitle-images' if caption else 'assets')/f'{len(copied):05d}_{local.name}'
                dest.parent.mkdir(exist_ok=True)
                shutil.copy2(local, dest)
                copied[key] = dest
            url.text = copied[key].as_uri().replace('file:///', 'file://localhost/')
    ET.indent(root)
    ET.ElementTree(root).write(target/'timeline.xml', encoding='utf-8', xml_declaration=True)
    rate = seq.find('rate')
    fps = int(rate.findtext('timebase', '25')) if rate is not None else 25
    if rate is not None and rate.findtext('ntsc') == 'TRUE':
        fps *= 1000/1001
    report = {**mapping.report(old_duration), 'unit': 'frames', 'fps': fps, 'kind': 'pr'}
    (target/'精剪合拢报告.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (target/'导入说明.txt').write_text('在 PR 导入 timeline.xml，打开名称带“精剪合拢”的新序列。原序列不变。\n'
        '字幕按视频相同的时间映射移动，字幕间合理的停顿保留；仅有视频的区间会保留。\n'
        '支持本工具生成的透明字幕画面轨；PR 原生字幕轨请先转为图形并确认 XML 中包含该轨。\n'
        'Final Cut Pro XML 的格式限制仍然存在，请复核第三方特效与图形。\n', encoding='utf-8')
    with zipfile.ZipFile(target/'result.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for p in target.rglob('*'):
            if p.is_file() and p.name != 'result.zip':
                archive.write(p, p.relative_to(target))
    return {**report, 'path': str(target/'timeline.xml'), 'name': title.text if title is not None else source.stem,
            'note': '在 PR 导入新 XML，打开“精剪合拢”序列。支持本工具的透明图片字幕轨；原序列保留。'}
