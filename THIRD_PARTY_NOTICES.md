# 引用、依赖与许可 / Credits and third-party licenses

Project-authored code and documentation: MIT, copyright 2026 wdddll1. This does not relicense dependencies, models, fonts, media or editor products. Complete license files captured from the build environment are under [docs/licenses](docs/licenses); package versions and notices are in [DEPENDENCIES.json](docs/DEPENDENCIES.json). Build-only packages may also appear in that inventory.

| Component / 材料 | Purpose / 用途 | License / 许可与来源 |
|---|---|---|
| [pyJianYingDraft 0.3.1](https://github.com/GuanYixuan/pyJianYingDraft) | Jianying draft generation / 剪映草稿结构 | Apache-2.0 |
| [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) | Local recognition and diarization / 本地推理 | Apache-2.0; bundled ONNX Runtime retains MIT terms |
| [Chinese Paraformer](https://huggingface.co/csukuangfj/sherpa-onnx-paraformer-zh-2023-09-14) | Chinese ASR / 中文识别 | Model card and upstream terms apply; downloaded separately |
| [English Zipformer small](https://huggingface.co/csukuangfj/sherpa-onnx-zipformer-small-en-2023-06-26) | English ASR / 英文识别 | Apache-2.0 model card; pinned revision in koubo/english.py; separate download |
| [Zipformer paper](https://arxiv.org/abs/2310.11230) | Recognition architecture reference / 架构文献 | Research citation, no paper text bundled |
| [pyannote segmentation 3.0](https://huggingface.co/pyannote/segmentation-3.0) | Speech segmentation / 说话分段 | Downloaded sherpa conversion carries its own LICENSE / model terms |
| [3D-Speaker](https://github.com/modelscope/3D-Speaker) | ERes2Net speaker embedding / 声纹 | Apache-2.0 project; model downloaded from sherpa release |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg/tree/v0.6.0) | FFmpeg discovery / 媒体工具下载 | BSD-2-Clause wrapper |
| [FFmpeg](https://ffmpeg.org/legal.html) | External media processing / 外部音视频处理 | Upstream Windows 7.1 essentials build uses GPLv3+; **not included in public ZIP** |
| [Gyan builds](https://www.gyan.dev/ffmpeg/builds/) | Upstream FFmpeg build provider / 二进制构建来源 | Downloaded directly from hash-verified imageio-ffmpeg wheel; see provider source/build information |
| [NumPy](https://numpy.org/) | Audio arrays / 音频数组 | BSD-3-Clause and bundled notices |
| [Pillow](https://python-pillow.github.io/) | Caption PNGs / 字幕图形 | HPND and bundled license terms |
| [HTTPX](https://github.com/encode/httpx) | AI requests / API 调用 | BSD-3-Clause |
| [pymediainfo](https://github.com/sbraz/pymediainfo) / [MediaInfo](https://mediaarea.net/MediaInfo) | Media metadata / 媒体信息 | MIT wrapper / BSD-2-Clause library |
| [uiautomation](https://github.com/yinkaisheng/Python-UIAutomation-for-Windows) | Dependency of draft library / 草稿库依赖 | Apache-2.0 |
| Python / Tcl / Tk | Portable runtime / 运行时 | PSF / Tcl-Tk terms; included notices |
| [PyInstaller](https://pyinstaller.org/) | Packaging / 打包 | GPL with bootloader exception; see included license |

The app generates its own scissors icon from the existing page brand design and a Windows system glyph. No Adobe/Jianying logos, executables or proprietary source are distributed. Windows system fonts remain system resources and are not bundled.

FFmpeg is acquired by the end user directly from upstream on first media use. Its executable is separate from this project's MIT code. A downloaded installation has additional licenses; redistributing a populated data/tools folder requires observing those terms, including applicable corresponding-source obligations. The public release intentionally contains no such executable or model weights.

已下载模型及工具不会因本项目采用 MIT 而改变许可。下载包只提供应用运行时，用户原素材、编辑结果和密钥不属于发布内容。本文引用的是工程依赖与研究资料，不声称获得 Adobe、剪映或模型作者的背书。
