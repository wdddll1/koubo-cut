"""Offline voice segmentation + 3D-Speaker embeddings; labels are anonymous."""
import hashlib
import json
import os
import shutil
import tarfile
import urllib.request
from pathlib import Path

SEGMENT_URL = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2'
EMBED_URL = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx'


def ready(directory):
    return all((Path(directory)/f).is_file() for f in ('segmentation.onnx', 'embedding.onnx'))


def download(directory, progress):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for index, (url, name) in enumerate(((SEGMENT_URL, 'segmentation.tar.bz2'), (EMBED_URL, 'embedding.onnx'))):
        final = directory/('segmentation.onnx' if index == 0 else name)
        if final.is_file():
            continue
        part = directory/(name+'.part')
        digest, size = hashlib.sha256(), 0
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'KouboCut/0.2'}), timeout=90) as response, part.open('wb') as output:
            total = int(response.headers.get('Content-Length', 0))
            while chunk := response.read(1024*1024):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
                progress(f'下载声纹模型 {index+1}/2：{size/1048576:.1f} MB', round(45*index + 45*size/total) if total else 10)
            if total and total != size:
                raise ValueError('声纹模型下载不完整，请重试')
        manifest[name] = {'url': url, 'bytes': size, 'sha256': digest.hexdigest()}
        if index == 0:
            # Extract only named regular files, never trust archive paths or links.
            with tarfile.open(part, 'r:bz2') as archive:
                for member in archive.getmembers():
                    leaf = Path(member.name).name
                    if member.isfile() and leaf in ('model.onnx', 'LICENSE', 'README.md'):
                        target = directory/('segmentation.onnx.part' if leaf == 'model.onnx' else 'segmentation-'+leaf)
                        with archive.extractfile(member) as src, target.open('wb') as dest:
                            shutil.copyfileobj(src, dest)
            os.replace(directory/'segmentation.onnx.part', final)
            part.unlink()
        else:
            os.replace(part, final)
    (directory/'download-info.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


def assign_tokens(tokens, segments):
    for token in tokens:
        scores = {}
        for segment in segments:
            overlap = max(0, min(token['end'], segment['end'])-max(token['start'], segment['start']))
            if overlap:
                scores[segment['speaker']] = scores.get(segment['speaker'], 0)+overlap
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        coverage = min(1, ranked[0][1]/(token['end']-token['start'])) if ranked else 0
        ambiguous = len(ranked) > 1 and ranked[1][1] > ranked[0][1]*0.35
        token['acoustic_speaker'] = ranked[0][0] if coverage >= 0.5 and not ambiguous else 'unknown'
        if not token.get('speaker_manual'):
            token['speaker'] = token['acoustic_speaker']
        token['speaker_status'] = 'overlap_or_uncertain' if ambiguous or coverage < 0.5 else 'acoustic_guess'
        token['speaker_coverage'] = round(coverage, 3)  # temporal coverage, NOT a calibrated identity probability


def annotated_text(project):
    lines, group = [], []
    def flush():
        if group:
            start, end = group[0]['start']/1000, group[-1]['end']/1000
            speaker = group[0].get('speaker', 'unknown')
            label = '人物 '+speaker if speaker != 'unknown' else '人物待定'
            lines.append(f'[{start:.3f}–{end:.3f} 秒] {label}：'+''.join(t.get('corrected_text',t['text']) for t in group))
            group.clear()
    for token in project.get('transcript', {}).get('tokens', []):
        if group and ((group[-1]['id'] in project.get('subtitle_breaks', [])) if project.get('editorial') else (token.get('speaker', 'unknown') != group[-1].get('speaker', 'unknown')
                      or token['start']-group[-1]['end'] > 600 or len(group) >= 30)):
            flush()
        group.append(token)
    flush()
    return '\n'.join(lines)+'\n'


def diarize(audio, duration, directory, count, progress):
    import sherpa_onnx as so
    from .media import read_audio
    if count not in (-1, 1, 2):
        raise ValueError('人物数量仅支持自动、1 人或 2 人')
    if not ready(directory):
        raise ValueError('请先下载说话人模型')
    config = so.OfflineSpeakerDiarizationConfig(
        segmentation=so.OfflineSpeakerSegmentationModelConfig(
            pyannote=so.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(Path(directory)/'segmentation.onnx')),
            num_threads=2, provider='cpu'),
        embedding=so.SpeakerEmbeddingExtractorConfig(model=str(Path(directory)/'embedding.onnx'), num_threads=2, provider='cpu'),
        clustering=so.FastClusteringConfig(num_clusters=count, threshold=0.5),
        min_duration_on=0.25, min_duration_off=0.35)
    if not config.validate():
        raise ValueError('说话人模型配置校验失败')
    engine = so.OfflineSpeakerDiarization(config)
    samples, rate = read_audio(audio)
    if rate != engine.sample_rate:
        raise ValueError('说话人识别需要 16kHz 音频')
    def callback(done, total):
        progress('本地声纹分组与语音活动检测', min(95, round(10+80*done/max(1,total))))
        return 0
    result = engine.process(samples, callback=callback).sort_by_start_time()
    names, segments = {}, []
    for item in result:
        if item.speaker not in names:
            n = len(names)
            names[item.speaker] = chr(65+n) if n < 26 else f'S{n+1}'
        start, end = max(0, round(item.start*1000)), min(duration, round(item.end*1000))
        if end > start:
            segments.append({'start': start, 'end': end, 'speaker': names[item.speaker]})
    return {'status': 'done', 'method': 'pyannote-3.0 + 3D-Speaker ERes2Net', 'requested_speakers': count,
            'speaker_count': len(names), 'segments': segments,
            'note': 'A/B 是本段素材中的匿名声纹分组，不代表真实姓名或屏幕人物位置。重叠发言、短句、配乐可能误判，请试听修正。'}
