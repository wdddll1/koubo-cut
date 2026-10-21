# Koubo Cut

[中文](README.md) · [English guide](docs/GUIDE.en.md) · [Downloads](https://github.com/wdddll1/koubo-cut/releases) · [Credits and licenses](THIRD_PARTY_NOTICES.md)

<img src="assets/logo.png" width="80" alt="Koubo Cut">

A local Windows rough-cut assistant for talking-head videos. Transcribe speech, review anonymous speaker labels and sentence boundaries, then create Jianying drafts or Premiere XML exchange packages. Optional AI actions correct transcripts, condense the entire video's content, and suggest a topic and title. After Effects is a placeholder only.

## Start

1. Download the Windows x64 ZIP from Releases, extract **all files** to a writable folder, and run `口播快剪.exe`. Python is bundled.
2. The first use requires internet access to download speech/speaker models and FFmpeg directly from upstream. The public ZIP includes neither model weights nor FFmpeg. Local recognition can then run offline.
3. Choose Jianying or Premiere, import a video, run local transcription and speaker grouping, and manually review speakers, sentence breaks and timing. Export using manual cuts or optional AI suggestions.
4. Use English / 中文 in the header. English selects a separate English Zipformer recognizer; Chinese uses Paraformer. Projects and transcript caches are isolated by language.

## Capabilities and limits

Timestamped Chinese/English recognition, manual speaker correction, sentence cuts, captions, review tracks, direct deletion, whole-video information retention, topic/title extraction, and post-edit gap closing with shared video/caption timing.

Jianying 5.9 drafts are supported. Premiere export uses **FCP 7 XML, transparent caption PNGs, and SRT**, not native .prproj or editable Premiere caption tracks. Keep all exchange files together. AE has no export implementation. Complex nested sequences, transitions, speed changes and other unsupported gap-close structures are rejected. Subtitle durations can be shorter than their video clips and retain their relative offset; in-editor hard binding is not guaranteed.

This is an unsigned Windows x64 beta. Timing and speaker groups require review; English word endings are estimated. Noise, overlapping speakers and accents can reduce accuracy. Adobe, Jianying and CapCut are not bundled or affiliated with this project. Other editor versions are not guaranteed.

## Portable layout and privacy

`口播快剪.exe`: launcher. `runtime/`: program dependencies. `data/`: projects, models, downloaded tools and caches. `docs/`: guides and notices. Copy the whole folder to preserve your environment. Remove personal data before sharing and observe licenses for any downloaded components you redistribute.

The server binds to loopback only. Media is not automatically uploaded. Explicit AI actions send transcript text, timestamps and speaker labels to your selected provider. API keys stay in process memory. Requests do not maintain conversation history; provider-side retention remains subject to that provider. Projects/transcripts persist locally. See [privacy](docs/PRIVACY.md).

## Development

Windows, Python 3.12:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python app.py --no-browser --port 8765
.\.venv\Scripts\python -m pytest tests -q
node --check static/app.js
node --check static/i18n.js
```

Open `http://127.0.0.1:8765/?lang=en`. Build instructions: [releasing](docs/RELEASING.md). Project source is MIT; third-party software/models retain their own terms. [Credits and licenses](THIRD_PARTY_NOTICES.md).
