"""Premiere interchange: legacy FCP XML (xmeml), linked audio, SRT and frame map."""
import copy
import json
import math
import os
import re
import time
import uuid
import zipfile
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

from pymediainfo import MediaInfo
from .core import srt_text, subtitle_cues
from .draft import black_png
from .review import review_subtitles
from .caption_images import caption_image


def rate_info(fps):
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError('素材帧率无效')
    for base in (24, 30, 60):
        if abs(fps - base * 1000 / 1001) < .01:
            return Fraction(base * 1000, 1001), base, True
    if abs(fps - round(fps)) < .001:
        return Fraction(round(fps)), round(fps), False
    raise ValueError('PR 首版支持整数帧率及 23.976/29.97/59.94，请先转为标准恒定帧率')


def frame_plan(project, plan, mode):
    fps, base, ntsc = rate_info(project['media']['fps'])
    frame = lambda ms: round(Fraction(round(ms), 1000) * fps)
    milliseconds = lambda f: round(Fraction(f * 1000, 1) / fps)
    source_frames = frame(project['media']['duration'])
    rows, cursor = [], 0
    for clip in plan['segments'] if mode == 'review' else plan['resolved_keep_ranges']:
        a, b = frame(clip['start']), min(source_frames, frame(clip['end']))
        if b <= a:
            continue
        start = a if mode == 'review' else cursor
        rows.append({**clip, 'source_in':a, 'source_out':b, 'timeline_in':start,
                     'timeline_out':start+b-a, 'category':clip.get('category','keep')})
        cursor = start+b-a
    if not rows:
        raise ValueError('PR 序列没有可保留的视频帧')
    mapped = copy.deepcopy(plan)
    if mode == 'review':
        mapped['segments'] = [{**r, 'start':milliseconds(r['source_in']), 'end':milliseconds(r['source_out']),
                               'target_start':milliseconds(r['timeline_in'])} for r in rows]
    else:
        mapped['resolved_keep_ranges'] = [{'start':milliseconds(r['source_in']), 'end':milliseconds(r['source_out']),
                                          'target_start':milliseconds(r['timeline_in'])} for r in rows]
    mapped['output_duration'] = milliseconds(source_frames if mode == 'review' else cursor)
    return rows, mapped, (fps, base, ntsc), source_frames


def export_premiere(project, plan, directory, subtitles=True, mode='review'):
    if mode not in ('review','compact'):
        raise ValueError('PR 工程模式无效')
    if str(project['media'].get('frame_rate_mode','')).upper() == 'VFR':
        raise ValueError('PR 帧级 XML 首版暂不支持可变帧率，请先转成恒定帧率再导入')
    rows, mapped, rate, source_frames = frame_plan(project,plan,mode)
    fps, base, ntsc = rate
    title = project.get('workflow',{}).get('draft_name') or Path(project['media']['name']).stem
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_',title)[:70].strip(' .') or '口播工程'
    name = f'PR_{title}_{time.strftime("%Y%m%d_%H%M%S")}_{uuid.uuid4().hex[:6]}'
    target = Path(directory)/'exports'/name
    target.mkdir(parents=True,exist_ok=False)
    width,height = project['media']['width'],project['media']['height']
    channels, sample_rate = 2, 48000
    info = MediaInfo.parse(project['source_path'])
    if info.audio_tracks:
        channels = int(info.audio_tracks[0].channel_s or 2)
        sample_rate = int(info.audio_tracks[0].sampling_rate or 48000)
    if channels not in (1,2):
        raise ValueError('PR 首版支持第一音轨的单声道或双声道，请先转换多声道素材')
    def el(parent, tag, value=None, **attrs):
        item = ET.SubElement(parent,tag,attrs)
        if value is not None: item.text=str(value)
        return item
    def add_rate(parent):
        item=el(parent,'rate');el(item,'timebase',base);el(item,'ntsc','TRUE' if ntsc else 'FALSE')
    def video_format(parent):
        el(parent,'width',width);el(parent,'height',height);el(parent,'anamorphic','FALSE')
        el(parent,'pixelaspectratio','square');el(parent,'fielddominance','none')
    root=ET.Element('xmeml',version='5')
    pr=el(root,'project');el(pr,'name',name)
    seq=el(el(pr,'children'),'sequence',id='koubo-sequence');el(seq,'name',title)
    duration=source_frames if mode=='review' else rows[-1]['timeline_out']
    el(seq,'duration',duration);add_rate(seq)
    tc=el(seq,'timecode');add_rate(tc);el(tc,'string','00:00:00:00');el(tc,'frame',0);el(tc,'displayformat','NDF')
    media=el(seq,'media');video=el(media,'video');fmt=el(el(video,'format'),'samplecharacteristics');add_rate(fmt);video_format(fmt)
    audio=el(media,'audio');el(audio,'numOutputChannels',channels)
    asample=el(el(audio,'format'),'samplecharacteristics');el(asample,'depth',16);el(asample,'samplerate',sample_rate)
    categories=['delete','no_dialogue','keep'] if mode=='review' else ['keep']
    labels={'delete':'建议删除待审核','no_dialogue':'无对话待审核','keep':'保留对话'}
    vt={};at={};vcount=0
    defined=set()
    def file_ref(parent, black=False):
        key='black-file' if black else 'source-file'
        node=el(parent,'file',id=key)
        if key in defined:return
        defined.add(key)
        el(node,'name','black.png' if black else project['media']['name'])
        # Absolute local references avoid importer-dependent relative path handling.
        el(node,'pathurl',(target/'black.png' if black else Path(project['source_path'])).resolve().as_uri().replace('file:///','file://localhost/'))
        add_rate(node);el(node,'duration',duration if black else source_frames)
        if black:el(node,'stillframe','TRUE')
        fm=el(node,'media');fvideo=el(el(fm,'video'),'samplecharacteristics');add_rate(fvideo);video_format(fvideo)
        if not black:
            fa=el(fm,'audio');sample=el(fa,'samplecharacteristics');el(sample,'depth',16);el(sample,'samplerate',sample_rate);el(fa,'channelcount',channels)
    if mode=='review':
        black_png(target/'black.png',width,height)
        track=el(video,'track');el(track,'enabled','TRUE');el(track,'locked','FALSE')
        item=el(track,'clipitem',id='black-clip');el(item,'name','黑色底板');el(item,'duration',duration);add_rate(item)
        for k,v in [('start',0),('end',duration),('in',0),('out',duration)]:el(item,k,v)
        file_ref(item,True);vcount=1
    for category in categories:
        vcount+=1
        track=el(video,'track');el(track,'enabled','TRUE');el(track,'locked','FALSE')
        vt[category]=(track,vcount)
        for channel in range(1,channels+1):
            atrack=el(audio,'track');el(atrack,'enabled','TRUE');el(atrack,'locked','FALSE')
            at[category,channel]=(atrack,len(at)+1)
    counts={c:0 for c in categories}
    for i,row in enumerate(rows):
        category=row['category'];counts[category]+=1;clip_index=counts[category]
        vid=f'video-{i}';links=[(vid,'video',vt[category][1])]+[(f'audio-{i}-{ch}','audio',at[category,ch][1]) for ch in range(1,channels+1)]
        for clipid,kind,trackindex in links:
            channel=next((ch for ch in range(1,channels+1) if clipid==f'audio-{i}-{ch}'),None)
            parent=vt[category][0] if kind=='video' else at[category,channel][0]
            item=el(parent,'clipitem',id=clipid);el(item,'name',f'{labels[category]} · {project["media"]["name"]}')
            el(item,'enabled','TRUE');el(item,'duration',source_frames);add_rate(item)
            for key,value in [('start',row['timeline_in']),('end',row['timeline_out']),('in',row['source_in']),('out',row['source_out'])]:el(item,key,value)
            file_ref(item)
            source=el(item,'sourcetrack');el(source,'mediatype',kind);el(source,'trackindex',channel or 1)
            if kind=='audio':el(item,'outputchannelindex',channel)
            for ref,mediatype,index in links:
                link=el(item,'link');el(link,'linkclipref',ref);el(link,'mediatype',mediatype);el(link,'trackindex',index);el(link,'clipindex',clip_index)
                if mediatype=='audio':el(link,'groupindex',1)
        marker=el(seq,'marker');el(marker,'name',labels[category]);el(marker,'in',row['timeline_in']);el(marker,'out',row['timeline_out'])
        people=sorted({t.get('speaker','unknown') for t in project.get('transcript',{}).get('tokens',[]) if row['start'] < t['end'] and row['end'] > t['start']})
        row['speakers']=people
        el(marker,'comment',f'原片 {row["start"]/1000:.3f}–{row["end"]/1000:.3f}s；人物 {", ".join(people) or "无对话"}')
    subtitle_count=0
    if subtitles:
        cues=review_subtitles(project,mapped) if mode=='review' else subtitle_cues(project,mapped)
        (target/'subtitles.srt').write_text(srt_text(cues),encoding='utf-8-sig')
        caption_track=el(video,'track');el(caption_track,'enabled','TRUE');el(caption_track,'locked','FALSE')
        plates=target/'subtitle-images';plates.mkdir()
        manifest=[];previous_end=0
        for cue in cues:
            start=max(previous_end,round(Fraction(round(cue['start']),1000)*fps))
            end=min(duration,round(Fraction(round(cue['end']),1000)*fps))
            if end<=start or not cue['text'].strip():continue
            index=len(manifest)+1
            image_path=plates/f'{index:05d}.png'
            caption_image(image_path,cue['text'],width,height)
            clip=el(caption_track,'clipitem',id=f'subtitle-{index}');el(clip,'name',cue['text'])
            el(clip,'enabled','TRUE');el(clip,'duration',duration);add_rate(clip)
            for key,value in [('start',start),('end',end),('in',0),('out',end-start)]:el(clip,key,value)
            file=el(clip,'file',id=f'subtitle-file-{index}');el(file,'name',image_path.name)
            el(file,'pathurl',image_path.resolve().as_uri().replace('file:///','file://localhost/'))
            add_rate(file);el(file,'duration',duration);el(file,'stillframe','TRUE')
            sample=el(el(el(file,'media'),'video'),'samplecharacteristics');add_rate(sample);video_format(sample)
            el(sample,'alphatype','straight')
            source=el(clip,'sourcetrack');el(source,'mediatype','video');el(source,'trackindex',1)
            manifest.append({**cue,'timeline_in':start,'timeline_out':end,'image':image_path.relative_to(target).as_posix()})
            previous_end=end
        subtitle_count=len(manifest)
        (target/'subtitle-manifest.json').write_text(json.dumps({'kind':'transparent_image_track','editable_text':False,'cues':manifest},ensure_ascii=False,indent=2),encoding='utf-8')
    ET.indent(root)
    (target/'timeline.xml').write_bytes(b'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n'+ET.tostring(root,encoding='utf-8'))
    (target/'edit_plan.json').write_text(json.dumps(mapped,ensure_ascii=False,indent=2),encoding='utf-8')
    (target/'frame_map.json').write_text(json.dumps({'timebase':base,'ntsc':ntsc,'fps':str(fps),'duration_frames':duration,'clips':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    (target/'PR导入说明.txt').write_text('''PR 工程交换包（不是原生 .prproj）
1. 将整个 ZIP 解压到一个固定文件夹，再在 Premiere 中使用 文件 → 导入，选择 timeline.xml。
2. 生成的序列保留引用原视频的切点和链接音频；分轨版 V1 黑底、V2 建议删除、V3 无对话、V4 保留对话；紧凑版仅连续保留片段。
3. 勾选字幕时，XML 已包含最上方的透明字幕画面轨，导入序列后自动显示，无需另行拖入 SRT。subtitle-images 文件夹必须保留。
   字幕画面可移动、裁剪和隐藏，但不是可改字的原生字幕。需要改字或字体时，先隐藏最上方字幕画面轨，再导入同包 subtitles.srt 并放在序列零点，使用 PR 原生字幕编辑，避免重叠。
   字幕尚未与视频删除联动，手动删片时请同步选择相应字幕。
4. 确认素材、声音、切点后另存为新的 .prproj，不覆盖已有工程。
5. XML 只引用原片，不包含原片。请勿移动原视频；换电脑需重新链接。
6. 如黑色底板或字幕图片离线，分别链接同文件夹 black.png 或 subtitle-images 内的 PNG。视频引用工具数据目录的原片；将工程包单独交给别人时需一并携带素材并重新链接。
所有切点按素材帧率取整；frame_map.json 记录原片帧、序列帧和人物标签，SRT 与帧级时间映射一致。
安装路径仅用于检测应用，不自动操作现有 PR 工程。
''',encoding='utf-8-sig')
    archive=Path(directory)/'premiere.partial.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for path in target.rglob('*'):
            if path.is_file():bundle.write(path,path.relative_to(target))
    os.replace(archive,Path(directory)/'premiere.zip')
    return {'path':str(target),'name':name,'mode':mode,'segments':len(rows),'format':'FCP7 XML','subtitle_clips':subtitle_count,
            'note':('已包含自动显示的透明字幕画面轨；可编辑文本另存于 SRT。' if subtitle_count else '未添加字幕画面。')+'完整解压并导入 timeline.xml，保留 subtitle-images 文件夹；在 PR 中另存 .prproj。'}
