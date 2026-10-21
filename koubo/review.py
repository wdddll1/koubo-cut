"""Lossless review timeline: mutually exclusive categories at source positions."""
from .core import complement, interval, merge_ranges, revision, subtitle_cues

TRACKS = {"keep": "画中画0 · 保留对话", "no_dialogue": "画中画1 · 无内容与语气助词待审核",
          "delete": "画中画2 · 建议删除待审核"}


def speech_regions(project):
    duration = project['media']['duration']
    diarization = project.get('diarization', {})
    if diarization.get('status') == 'done':
        # Both VAD and recognized speech protect a region from the empty track.
        ranges = [[s['start'], s['end']] for s in diarization.get('segments', [])]
        ranges += [[max(0, t['start']-120), min(duration, t['end']+160)]
                   for t in project.get('transcript', {}).get('tokens', [])]
        return merge_ranges(ranges)
    # Without VAD, only actual acoustic silence is classified as no dialogue.
    recognized = [[max(0, t['start']-120), min(duration,t['end']+160)]
                  for t in project.get('transcript', {}).get('tokens', [])]
    return merge_ranges(complement(project.get('silences', []), duration)+recognized)


def compile_review_plan(project):
    if project.get('workflow',{}).get('manual_cut'):
        from .sentences import manual_cut_project
        project=manual_cut_project(project)
    duration = project['media']['duration']
    sentence_mode = project.get('editing_policy')=='sentences'
    sentences = project.get('editorial',{}).get('sentences',[])
    nonspeech = complement(speech_regions(project), duration)
    # An ASR token wins over a false acoustic silence detection.
    tokens = project.get('transcript', {}).get('tokens', [])
    nonspeech = [[a, b] for a, b in nonspeech if b-a >= 350]
    if sentence_mode:
        nonspeech = [[a,b] for a,b in nonspeech if b-a>=1200 and sentences and not any(a<s['end'] and b>s['start'] for s in sentences)]
    boundaries = {0, duration}
    if sentence_mode:
        boundaries.update(s['start'] for s in sentences[1:])
    candidates = project.get('candidates', [])
    for c in candidates:
        interval(c['start'], c['end'], duration)
        boundaries.update((c['start'], c['end']))
    for a, b in nonspeech:
        boundaries.update((a, b))
    for a, b in zip(tokens, tokens[1:]):
        if not sentence_mode and a.get('speaker') != b.get('speaker'):
            boundaries.add((a['end']+b['start'])//2)
    for key in ([] if sentence_mode else project.get('subtitle_breaks', [])):
        t = next((t for t in tokens if t['id'] == key), None)
        if t:
            boundaries.add(t['end'])
    fps = round(project['media'].get('fps', 0))
    if fps > 0:
        # Silence handles and speaker estimates can differ by a few milliseconds.
        # Snap to the draft frame grid so no 6 ms/unselectable picture fragments appear.
        frame = 1000/fps
        boundaries = {max(0, min(duration, round(round(p/frame)*frame))) for p in boundaries}
        boundaries.update((0, duration))
        boundaries = {p for p in boundaries if p in (0, duration) or (p >= frame*0.5 and duration-p >= frame*0.5)}
    segments = []
    points = sorted(boundaries)
    for a, b in zip(points, points[1:]):
        covering = [c for c in candidates if (c['start'] <= (a+b)/2 < c['end'] if sentence_mode else c['start'] < b and c['end'] > a)]
        overrides = [c for c in covering if c.get('review_action', 'auto') != 'auto']
        # Explicit keep has highest priority; a transition can always be restored.
        if any(c['review_action'] == 'keep' for c in overrides):
            kind = 'keep'
        elif overrides:
            kind = 'delete' if any(c['review_action'] == 'delete' for c in overrides) else 'no_dialogue'
        elif any(c.get('kind')=='filler' for c in covering):
            kind = 'no_dialogue'
        elif any(a < y and b > x for x, y in nonspeech) and not any(t['start'] < b and t['end'] > a for t in tokens):
            kind = 'no_dialogue'
        elif any(c.get('kind') in ('ai', 'repeat') or (c.get('accepted') and c.get('kind') != 'silence') for c in covering):
            kind = 'delete'
        else:
            kind = 'keep'
        speakers = sorted({t.get('speaker', 'unknown') for t in tokens if t['start'] < b and t['end'] > a})
        segments.append({'id': f'clip_{len(segments):05d}', 'start': a, 'end': b,
                         'target_start': a, 'category': kind, 'track': TRACKS[kind],
                         'speakers': speakers, 'candidate_ids': [c['id'] for c in covering]})
    return {'schema_version': '2.0-review', 'mode': 'review', 'time_unit': 'ms',
            'source_id': project['source_id'], 'source_path': project['source_path'],
            'source_duration': duration, 'output_duration': duration,
            'transcript_revision': revision(project.get('transcript', {})),
            'boundary_policy': 'internal cuts snapped to draft frames' if fps else 'source milliseconds',
            'segments': segments, 'black_base': {'start': 0, 'end': duration},
            'track_order_bottom_to_top': ['黑色主轨道', TRACKS['delete'], TRACKS['no_dialogue'], TRACKS['keep']],
            'note': '所有片段保留原位置及声音，审核草稿不会自动缩短；AI建议含尚未勾选确认的项目。'}


def review_subtitles(project, plan):
    cues = []
    for segment in plan['segments']:
        mapping = {'resolved_keep_ranges': [{'start': segment['start'], 'end': segment['end'],
                                           'target_start': segment['start']}]}
        # If a manual/frame cut straddles an estimated word, attach its text once.
        # This avoids duplicating the same character in adjacent subtitle clips.
        tokens = [t for t in project.get('transcript', {}).get('tokens', [])
                  if segment['start'] <= (t['start']+t['end'])/2 < segment['end']]
        fragment = {**project, 'transcript':{**project.get('transcript', {}), 'tokens':tokens}}
        for cue in subtitle_cues(fragment, mapping):
            cues.append({**cue, 'clip_id': segment['id'], 'category': segment['category']})
    return cues
