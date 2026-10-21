import hashlib
import math
import os
import re
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from pymediainfo import MediaInfo


def ffmpeg():
    from .runtime_tools import ffmpeg_path
    return ffmpeg_path()


def run_ffmpeg(arguments, timeout=3600):
    result = subprocess.run([ffmpeg(), "-hide_banner", "-nostdin", *map(str, arguments)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=timeout)
    if result.returncode:
        raise ValueError("媒体处理失败：" + result.stderr.decode("utf-8", "replace")[-1800:])
    return result.stderr.decode("utf-8", "replace")


def source_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_video(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file() or path.suffix.lower() not in {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}:
        raise ValueError("请选择 MP4、MOV、MKV、AVI、M4V 或 WebM 视频")
    info = MediaInfo.parse(str(path))
    if not info.video_tracks or not info.audio_tracks:
        raise ValueError("需要至少一条视频轨和一条音轨")
    video, audio = info.video_tracks[0], info.audio_tracks[0]
    duration = round(float(video.duration or info.general_tracks[0].duration))
    if not 500 <= duration <= 2 * 3600 * 1000:
        raise ValueError("测试版支持 0.5 秒至 2 小时的视频")
    # Delay is relative to the video stream, in milliseconds. Refuse unusual sync
    # rather than silently producing a drifting project.
    delay = float(getattr(audio, "delay_relative_to_video", 0) or 0)
    if abs(delay) > 80:
        raise ValueError(f"音轨相对视频偏移 {delay:g} ms，测试版暂不支持，请先在剪映导出同步后的原速素材")
    rotation = float(getattr(video, "rotation", 0) or 0)
    if abs(rotation) > 0.1:
        raise ValueError("该视频带有旋转元数据。请先导出方向正确的视频再测试，以免剪映与浏览器显示方向不一致")
    return {"duration": duration, "width": int(video.width), "height": int(video.height),
            "fps": float(video.frame_rate or 30), "audio_tracks": len(info.audio_tracks),
            "frame_rate_mode": getattr(video, "frame_rate_mode", ""), "audio_delay_ms": delay,
            "bytes": path.stat().st_size, "name": path.name}


def prepare_audio(source, directory):
    directory = Path(directory)
    audio = directory / "analysis.wav"
    part = directory / "analysis.partial.wav"
    if not audio.exists():
        run_ffmpeg(["-y", "-i", source, "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", part])
        os.replace(part, audio)
    return audio


def read_audio(path):
    with wave.open(str(path), "rb") as source:
        rate = source.getframerate()
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError("识别音频必须是单声道 16-bit WAV")
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    return samples, rate


def detect_silence(audio, duration, db=-38):
    log = run_ffmpeg(["-i", audio, "-af", f"silencedetect=noise={db}dB:d=0.35", "-f", "null", "-"])
    ranges, start = [], None
    for kind, value in re.findall(r"silence_(start|end):\s*([\d.]+)", log):
        moment = max(0, min(duration, round(float(value) * 1000)))
        if kind == "start":
            start = moment
        elif start is not None and moment > start:
            ranges.append([start, moment])
            start = None
    if start is not None and start < duration:
        ranges.append([start, duration])
    return ranges


def recognition_chunks(duration, silences, max_ms=25000):
    """Partition without dropping or duplicating time. Prefer centers of silences."""
    boundaries = [(a + b) // 2 for a, b in silences if b - a >= 350]
    start, chunks = 0, []
    while start < duration:
        end = min(duration, start + max_ms)
        if end < duration:
            choices = [b for b in boundaries if start + 8000 <= b <= end]
            if choices:
                end = choices[-1]
        chunks.append([start, end])
        start = end
    return chunks


def transcribe(audio, media, silences, model_dir, progress):
    import sherpa_onnx
    model_dir = Path(model_dir)
    if not (model_dir / "model.int8.onnx").is_file() or not (model_dir / "tokens.txt").is_file():
        raise ValueError("中文识别模型尚未准备，请先点击「下载识别模型」")
    progress("加载本地 Paraformer 模型", 5)
    recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
        paraformer=str(model_dir / "model.int8.onnx"), tokens=str(model_dir / "tokens.txt"),
        num_threads=min(6, max(1, (os.cpu_count() or 4) // 2)), provider="cpu", debug=False)
    samples, rate = read_audio(audio)
    chunks = recognition_chunks(media["duration"], silences)
    tokens, segments, warnings = [], [], []
    for chunk_index, (start, end) in enumerate(chunks):
        progress(f"识别第 {chunk_index + 1}/{len(chunks)} 段", 10 + round(85 * chunk_index / len(chunks)))
        signal = samples[round(start * rate / 1000):round(end * rate / 1000)]
        if len(signal) == 0 or float(np.max(np.abs(signal))) < 0.001:
            continue
        stream = recognizer.create_stream()
        stream.accept_waveform(rate, signal)
        recognizer.decode_stream(stream)
        result = stream.result
        text, pieces, times = result.text.strip(), list(result.tokens), list(result.timestamps)
        if not text:
            continue
        if len(pieces) != len(times) or not times:
            warnings.append(f"第 {chunk_index + 1} 段没有完整字词时间戳，只能整段复核")
            tokens.append({"id": f"t{len(tokens) + 1:06}", "text": text, "start": start, "end": end,
                           "aligned": False, "timing": "segment_only"})
        else:
            for i, piece in enumerate(pieces):
                clean = piece.replace("@@", "").replace("▁", " ")
                if not clean.strip():
                    continue
                t0 = max(start, min(end - 1, start + round(times[i] * 1000)))
                next_start = start + round(times[i + 1] * 1000) if i + 1 < len(times) else end
                # Model predicts starts only. Bound estimated ends conservatively;
                # never advertise these estimates as forced-alignment end times.
                t1 = min(end, next_start, t0 + (500 if i + 1 == len(times) else 700))
                t0 = max(t0, tokens[-1]["end"] if tokens else 0)
                if t1 <= t0:
                    warnings.append(f"第 {chunk_index + 1} 段有重合时间戳，相关字词未用于自动建议")
                    continue
                tokens.append({"id": f"t{len(tokens) + 1:06}", "text": clean, "start": t0, "end": t1,
                               "aligned": True, "timing": "model_start_estimated_end"})
        segments.append({"id": f"s{len(segments) + 1:04}", "start": start, "end": end, "text": text})
    if not tokens:
        raise ValueError("未识别到语音，请检查音轨、音量和素材语言")
    return {"engine": "sherpa-onnx/paraformer-zh-2023-09-14-int8", "tokens": tokens,
            "segments": segments, "warnings": warnings,
            "timing_note": "模型提供字词起点，结束时间根据后继起点估算；切点必须试听。"}


def create_proxy(source, output):
    run_ffmpeg(["-y", "-i", source, "-map", "0:v:0", "-map", "0:a:0", "-vf",
                "scale=trunc(iw*min(1\\,720/iw)/2)*2:trunc(ih*min(1\\,720/iw)/2)*2",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-c:a", "aac",
                "-movflags", "+faststart", output])


def render_video(source, plan, output, directory, progress):
    """Trim on decoded media and concatenate before encoding audio once.

    Encoding AAC separately per cut would accumulate encoder padding. A filter
    script also avoids the Windows command-line length limit for many cuts.
    """
    graph, inputs = [], []
    keeps = plan["resolved_keep_ranges"]
    for i, keep in enumerate(keeps):
        start, end = keep["start"] / 1000, keep["end"] / 1000
        graph.append(f"[0:v:0]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{i}]")
        graph.append(f"[0:a:0]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{i}]")
        inputs.extend([f"[v{i}]", f"[a{i}]"])
    graph.append("".join(inputs) + f"concat=n={len(keeps)}:v=1:a=1[vout][aout]")
    script = Path(directory) / "render-filter.txt"
    script.write_text(";\n".join(graph), encoding="ascii")
    partial = Path(directory) / "edited.partial.mp4"
    progress(f"渲染 {len(keeps)} 个保留片段（统一编码音频）", 10)
    run_ffmpeg(["-y", "-i", source, "-filter_complex_script", script,
                "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-preset", "fast",
                "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart", partial])
    os.replace(partial, output)
    script.unlink(missing_ok=True)
    progress("视频已生成", 100)
