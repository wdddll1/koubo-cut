import copy
import json
import math

import httpx
import pytest

from koubo.ai import request_suggestions
from koubo.core import (compile_plan, complement, interval, merge_ranges,
                        resolve_tokens, rule_candidates, srt_text, subtitle_cues, validate_llm_response)
from koubo.media import recognition_chunks


@pytest.fixture
def project():
    return {"source_id": "abc", "source_path": "original.mp4", "media": {"duration": 10000},
            "transcript": {"tokens": [{"id": f"t{i:03}", "text": text, "start": start, "end": end,
                                         "aligned": True} for i, (text, start, end) in enumerate([
                ("今天", 500, 900), ("讲", 950, 1200), ("今天", 1500, 1900), ("讲", 1950, 2200),
                ("三个", 2500, 3000), ("问题", 3200, 3600), ("结束", 8000, 8500)])]},
            "silences": [[4000, 7500]], "candidates": []}


def test_overlap_union_does_not_shift_source_time(project):
    project["candidates"] = [{"accepted": True, "start": a, "end": b} for a, b in [(1000, 3000), (2000, 4000), (6000, 7000)]]
    plan = compile_plan(project)
    assert plan["resolved_delete_ranges"] == [[1000, 4000], [6000, 7000]]
    assert plan["resolved_keep_ranges"] == [
        {"start": 0, "end": 1000, "target_start": 0},
        {"start": 4000, "end": 6000, "target_start": 1000},
        {"start": 7000, "end": 10000, "target_start": 3000}]
    assert plan["output_duration"] == 6000


@pytest.mark.parametrize("a,b", [(math.nan, 200), (0, math.inf), (True, 30), (-1, 10), (20, 10), (0, 11000)])
def test_reject_invalid_intervals(a, b):
    with pytest.raises(ValueError):
        interval(a, b, 10000)


def test_prevent_deleting_entire_video(project):
    project["candidates"] = [{"accepted": True, "start": 0, "end": 10000}]
    with pytest.raises(ValueError, match="整个视频"):
        compile_plan(project)


def test_only_accepted_decisions_apply(project):
    project["candidates"] = [{"accepted": False, "start": 1000, "end": 9000}]
    assert compile_plan(project)["output_duration"] == 10000


def test_fake_or_reversed_ai_ids_do_not_pass(project):
    for first, last in [("unknown", "t002"), ("t003", "t000")]:
        with pytest.raises(ValueError):
            validate_llm_response({"deletions": [{"from_token": first, "to_token": last, "reason": "重复"}]}, project)


def test_missing_alignment_is_not_automatic_cut(project):
    project["transcript"]["tokens"][0]["aligned"] = False
    with pytest.raises(ValueError, match="时间戳"):
        resolve_tokens(project["transcript"]["tokens"], "t000", "t001", 10000)


def test_rule_suggestions_pending_and_keep_pause_handles(project):
    suggestions = rule_candidates(project, 900, 320)
    assert all(c["accepted"] is False for c in suggestions)
    assert any(c["kind"] == "repeat" for c in suggestions)
    silence = next(c for c in suggestions if c["kind"] == "silence")
    assert [silence["start"], silence["end"]] == [4160, 7340]


def test_subtitles_split_at_cut_and_retime(project):
    project["candidates"] = [{"accepted": True, "start": 1200, "end": 2500}]
    cues = subtitle_cues(project, compile_plan(project))
    assert "今天讲" == cues[0]["text"]
    assert cues[1]["start"] == 1200
    assert all(c["end"] <= 8700 for c in cues)
    text = srt_text(cues)
    assert "00:00:01,200" in text


def test_partition_has_no_gaps_and_uses_silence():
    chunks = recognition_chunks(75000, [[18000, 20000], [42000, 43000]])
    assert chunks[0] == [0, 19000]
    assert chunks[-1][1] == 75000
    assert all(a[1] == b[0] for a, b in zip(chunks, chunks[1:]))


def test_edge_silence_does_not_leave_isolated_tiny_clips(project):
    project['silences'] = [[0, 2000], [8000, 10000]]
    candidates = [c for c in rule_candidates(project) if c['kind'] == 'silence']
    assert candidates[0]['start'] == 0
    assert candidates[-1]['end'] == 10000


def test_deepseek_adapter_schema_and_safe_error():
    captured = []
    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"deletions":[]}'}}]})
    result = request_suggestions("deepseek", "test-model", "secret-test-only", "转录文字", httpx.MockTransport(handler))
    assert result == {"deletions": []}
    assert captured[0]["response_format"] == {"type": "json_object"}
    with pytest.raises(ValueError, match="HTTP 401") as caught:
        request_suggestions("deepseek", "test-model", "secret-test-only", "文稿",
                            httpx.MockTransport(lambda request: httpx.Response(401, json={"error": "secret-test-only"})))
    assert "secret-test-only" not in str(caught.value)


def test_openai_adapter_and_incomplete_rejection():
    def handler(request):
        body = json.loads(request.content)
        assert body["text"]["format"]["strict"] is True
        assert body["store"] is False
        return httpx.Response(200, json={"status": "completed", "output": [{"content": [{"type": "output_text", "text": '{"deletions":[]}'}]}]})
    assert request_suggestions("openai", "test-model", "test-key", "文字", httpx.MockTransport(handler)) == {"deletions": []}
    with pytest.raises(ValueError, match="未完成"):
        request_suggestions("openai", "test-model", "test-key", "文字", httpx.MockTransport(
            lambda request: httpx.Response(200, json={"status": "incomplete"})))
