"""Pure editing logic. All intervals use original-media milliseconds, [start, end)."""
import hashlib
import json
import math
import re


def number(value, label="时间"):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label}必须是有限数值")
    return round(value)


def interval(start, end, duration):
    start, end = number(start), number(end)
    if not 0 <= start < end <= duration:
        raise ValueError(f"无效区间 {start}–{end}，素材时长 {duration} ms")
    return [start, end]


def merge_ranges(ranges):
    result = []
    for start, end in sorted(ranges):
        if result and start <= result[-1][1]:
            result[-1][1] = max(end, result[-1][1])
        else:
            result.append([start, end])
    return result


def complement(deletes, duration):
    cursor, keeps = 0, []
    for start, end in merge_ranges(deletes):
        if start > cursor:
            keeps.append([cursor, start])
        cursor = end
    if cursor < duration:
        keeps.append([cursor, duration])
    return keeps


def subtract_ranges(ranges, protected):
    result = []
    for a,b in merge_ranges(ranges):
        cursor = a
        for x,y in merge_ranges(protected):
            if y <= cursor or x >= b:
                continue
            if x > cursor:
                result.append([cursor,min(x,b)])
            cursor = max(cursor,y)
        if cursor < b:
            result.append([cursor,b])
    return result


def revision(transcript):
    data = json.dumps(transcript, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def validate_tokens(tokens, duration):
    seen, previous = set(), -1
    for token in tokens:
        if not isinstance(token.get("id"), str) or token["id"] in seen:
            raise ValueError("字词 ID 缺失或重复")
        seen.add(token["id"])
        interval(token["start"], token["end"], duration)
        if token["start"] < previous:
            raise ValueError("字词时间顺序错误")
        previous = token["end"]
        if not isinstance(token.get("text"), str) or not token["text"].strip():
            raise ValueError("字词文本为空")


def resolve_tokens(tokens, first, last, duration, padding=60):
    index = {token["id"]: i for i, token in enumerate(tokens)}
    if first not in index or last not in index:
        raise ValueError("模型返回了不存在的字词 ID")
    left, right = index[first], index[last]
    if left > right:
        raise ValueError("字词范围方向错误")
    selected = tokens[left:right + 1]
    if any(not t.get("aligned", True) for t in selected):
        raise ValueError("该区间缺少可靠时间戳，请手工选择时间")
    # Include selected utterance edges but never cross adjacent token boundaries.
    start = max(tokens[left - 1]["end"] if left else 0, selected[0]["start"] - padding)
    end = min(tokens[right + 1]["start"] if right + 1 < len(tokens) else duration,
              selected[-1]["end"] + padding)
    return interval(start, end, duration)


def make_candidate(kind, start, end, reason, text="", **extra):
    identity = f"{kind}:{start}:{end}:{extra.get('from_token', '')}:{extra.get('to_token', '')}"
    return {"id": hashlib.sha256(identity.encode()).hexdigest()[:16], "kind": kind,
            "start": start, "end": end, "reason": reason, "text": text,
            "accepted": False, **extra}


def rule_candidates(project, threshold=900, keep=320):
    threshold, keep = number(threshold), number(keep)
    if not 400 <= threshold <= 10000 or not 160 <= keep <= threshold:
        raise ValueError("停顿阈值需为 400–10000 ms，保留停顿需为 160 ms 至阈值之间")
    output = []
    duration = project["media"]["duration"]
    for start, end in project.get("silences", []):
        if end - start < threshold:
            continue
        # Keep natural handles at both ends. No silence is accepted automatically.
        a, b = start + keep // 2, end - keep // 2
        if start <= 40:
            a = 0
        if end >= duration - 40:
            b = duration
        if b > a:
            output.append(make_candidate("silence", a, b, "检测到较长静音，建议缩短；请试听确认", "静音"))
    tokens = project.get("transcript", {}).get("tokens", [])
    # Only exact adjacent repeats (2–12 tokens); no generic filler-word deletion.
    occupied = set()
    for size in range(12, 1, -1):
        for i in range(len(tokens) - 2 * size + 1):
            if any(k in occupied for k in range(i, i + size)):
                continue
            a, b = tokens[i:i + size], tokens[i + size:i + 2 * size]
            if [t["text"] for t in a] != [t["text"] for t in b]:
                continue
            # In a dialogue, repeating the other person's words may be a reply.
            if len({t.get('speaker', 'unknown') for t in a+b}) > 1:
                continue
            if b[0]["start"] - a[-1]["end"] > 2200:
                continue
            try:
                start, end = resolve_tokens(tokens, a[0]["id"], a[-1]["id"], duration)
            except ValueError:
                continue
            output.append(make_candidate("repeat", start, end, "相邻内容完全重复，建议删除第一次；可能是强调，请确认",
                                         "".join(t["text"] for t in a),
                                         from_token=a[0]["id"], to_token=a[-1]["id"]))
            occupied.update(range(i, i + size))
    return sorted(output, key=lambda x: (x["start"], x["end"]))


def validate_llm_response(data, project):
    if not isinstance(data, dict) or not isinstance(data.get("deletions"), list):
        raise ValueError("AI 返回格式不正确：需要 deletions 数组")
    if len(data["deletions"]) > 300:
        raise ValueError("AI 返回过多删除建议")
    tokens = project["transcript"]["tokens"]
    index = {t["id"]: i for i, t in enumerate(tokens)}
    output = []
    for item in data["deletions"]:
        if not isinstance(item, dict):
            raise ValueError("AI 建议必须为对象")
        first, last = item.get("from_token"), item.get("to_token")
        if not isinstance(first, str) or not isinstance(last, str):
            raise ValueError("AI 字词 ID 格式错误")
        start, end = resolve_tokens(tokens, first, last, project["media"]["duration"])
        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("AI 删除理由缺失")
        text = "".join(t["text"] for t in tokens[index[first]:index[last] + 1])
        protected = bool(re.search(r"[0-9零一二三四五六七八九十百千万亿不没无非仅只除必须条件如果否则]", text))
        output.append(make_candidate("ai", start, end, reason[:500], text,
                                     from_token=first, to_token=last, protected=protected))
    return output


def compile_plan(project):
    duration = project["media"]["duration"]
    decisions = []
    for item in project.get("candidates", []):
        if item.get("accepted") is True:
            interval(item["start"], item["end"], duration)
            decisions.append({**item, "action": "delete"})
    protected = [interval(c['start'],c['end'],duration) for c in project.get('candidates', []) if c.get('review_action') == 'keep']
    deletes = subtract_ranges([[d["start"], d["end"]] for d in decisions], protected)
    keeps = complement(deletes, duration)
    if not keeps:
        raise ValueError("不能删除整个视频，请至少保留一个片段")
    cursor, mapped, warnings = 0, [], []
    for start, end in keeps:
        if end - start < 250:
            warnings.append(f"保留区间 {start}–{end} ms 不足 250 ms，请试听")
        mapped.append({"start": start, "end": end, "target_start": cursor})
        cursor += end - start
    return {"schema_version": "1.0", "source_id": project["source_id"],
            "source_path": project["source_path"], "time_unit": "ms",
            "transcript_revision": revision(project.get("transcript", {})),
            "decisions": decisions, "resolved_delete_ranges": deletes,
            'protected_keep_ranges':merge_ranges(protected),
            "resolved_keep_ranges": mapped, "source_duration": duration,
            "output_duration": cursor, "warnings": warnings}


def subtitle_cues(project, plan):
    """Split at edits; every cue is mapped from source to the new timeline."""
    cues = []
    sentence_mode = project.get("editing_policy")=="sentences"
    from .sentences import preview_breaks
    breaks = preview_breaks(project) if sentence_mode else project.get("subtitle_breaks",[])
    for keep in plan["resolved_keep_ranges"]:
        current = []
        for token in project.get("transcript", {}).get("tokens", []):
            start, end = max(token["start"], keep["start"]), min(token["end"], keep["end"])
            if end <= start:
                continue
            mapped = {"start": keep["target_start"] + start - keep["start"],
                      "end": keep["target_start"] + end - keep["start"], "text": token.get("corrected_text",token["text"])}
            mapped['speaker'] = token.get('speaker', 'unknown')
            if current and ((not sentence_mode and (len(current) >= 18 or mapped["start"] - current[-1]["end"] > 500))
                            or (not sentence_mode and mapped['speaker'] != current[-1]['speaker'])
                            or current[-1].get('id') in breaks):
                cues.append({"start": current[0]["start"], "end": current[-1]["end"],
                             "text": "".join(t["text"] for t in current)})
                current = []
            mapped['id'] = token['id']
            current.append(mapped)
        if current:
            cues.append({"start": current[0]["start"], "end": current[-1]["end"],
                         "text": "".join(t["text"] for t in current)})
    return cues


def srt_text(cues):
    def stamp(ms):
        hours, ms = divmod(round(ms), 3600000)
        minutes, ms = divmod(ms, 60000)
        seconds, ms = divmod(ms, 1000)
        return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"
    return "\n\n".join(f"{i}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text']}"
                          for i, c in enumerate(cues, 1)) + "\n"
