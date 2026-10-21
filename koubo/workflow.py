"""Per-video options and one authoritative compact export plan."""
import re

from .core import compile_plan, make_candidate
from .review import compile_review_plan

DEFAULTS = {'manual_cut': False, 'compression_enabled': False, 'retention': 70, 'direct_delete': False,
            'draft_name': '', 'speakers': -1, 'subtitles': True, 'draft_mode': 'review'}


def validate_options(data):
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise ValueError('页面配置字段无效')
    result = {**DEFAULTS, **data}
    for key in ('manual_cut', 'compression_enabled', 'direct_delete', 'subtitles'):
        if not isinstance(result[key], bool):
            raise ValueError('选项状态必须为布尔值')
    if type(result['retention']) is not int or not 20 <= result['retention'] <= 100:
        raise ValueError('信息保留目标必须为 20–100 的整数')
    if type(result['speakers']) is not int or result['speakers'] not in (-1, 1, 2):
        raise ValueError('人物数量仅支持自动、1 人或 2 人')
    if result['draft_mode'] not in ('review', 'compact'):
        raise ValueError('草稿模式无效')
    if not isinstance(result['draft_name'], str) or len(result['draft_name']) > 80:
        raise ValueError('草稿名称最多 80 字')
    result['draft_name'] = result['draft_name'].strip()
    return result


def compact_plan(project):
    if project.get('workflow',{}).get('manual_cut'):
        from .sentences import manual_cut_project
        local=manual_cut_project(project)
        plan=compact_plan(local)
        boundaries=sorted(s['start'] for s in local['editorial']['sentences'][1:])
        pieces=[]
        for keep in plan['resolved_keep_ranges']:
            points=[keep['start']]+[p for p in boundaries if keep['start']<p<keep['end']]+[keep['end']]
            pieces.extend({'start':a,'end':b,'target_start':keep['target_start']+a-keep['start']} for a,b in zip(points,points[1:]))
        plan['resolved_keep_ranges']=pieces
        plan['manual_cut']=True
        return plan
    if not project.get('workflow', {}).get('direct_delete'):
        return compile_plan(project)
    review = compile_review_plan(project)
    # Exactly the delete lane is removed; protected transitions and empty footage survive.
    candidates = [make_candidate('manual', s['start'], s['end'], '直接删除建议轨道', accepted=True)
                  for s in review['segments'] if s['category'] == 'delete']
    plan = compile_plan({**project, 'candidates': candidates})
    plan['mode'] = 'direct_delete'
    return plan


def retention_report(project):
    review = compile_review_plan(project)
    tokens = project.get('transcript', {}).get('tokens', [])
    total = kept = 0
    for token in tokens:
        weight = len(re.sub(r'[^\w\u4e00-\u9fff]', '', token['text']))
        total += weight
        mid = (token['start'] + token['end']) / 2
        if not any(s['category'] == 'delete' and s['start'] <= mid < s['end'] for s in review['segments']):
            kept += weight
    actual = round(100 * kept / total, 1) if total else None
    config = project.get('workflow', {})
    target = config.get('retention') if config.get('compression_enabled') else None
    analysis = project.get('ai_analysis', {})
    stale = (config.get('compression_enabled', False) and not analysis) or bool(analysis) and (analysis.get('compression_enabled', False) != config.get('compression_enabled', False)
                              or analysis.get('retention', 70) != config.get('retention', 70))
    return {'target': target, 'actual': actual, 'kept_characters': kept, 'total_characters': total,
            'needs_reanalysis': stale, 'unit': '有效文稿字数；不是语义信息量或视频时长',
            'off_target': target is not None and actual is not None and abs(target - actual) > 10}
