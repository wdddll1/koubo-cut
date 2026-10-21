# 口播快剪 · Koubo Cut

[English](README.en.md) · [中文教程](docs/GUIDE.zh-CN.md) · [下载软件](https://github.com/wdddll1/koubo-cut/releases) · [引用与许可](THIRD_PARTY_NOTICES.md)

<img src="assets/logo.png" width="80" alt="Koubo Cut">

Windows 本地口播粗剪工具：识别文稿与说话人，人工复核断句，按时间戳制作剪映草稿或 Premiere 工程交换包。AI 校正文稿、全片信息浓缩和主题标题提炼均为可选操作。AE 目前仅有占位入口。

## 快速开始

1. 从 Releases 下载 Windows x64 ZIP，**完整解压**到可写文件夹，双击 `口播快剪.exe`。无需安装 Python。
2. 首次使用需要联网下载当前语言的语音模型、声纹模型和媒体工具；公开 ZIP 不携带模型与 FFmpeg。之后本地识别可以离线进行。
3. 选择剪映或 PR，导入视频，执行本地文稿和说话人识别，人工复核人物、断句与切点，再选择手工直剪或 AI 分析后生成工程。
4. 页面右上角 English / 中文切换界面与识别语言。英文使用独立 Zipformer，中文保持 Paraformer；项目列表与转录缓存按语言隔离。

## 功能与边界

- 本地中文 / 英文带时间戳识别；匿名说话人 A/B 分组及人工修正。
- 句子切片、字幕、删除建议、无内容轨道、手工直剪、全片信息保留比例。
- 剪映 5.9 草稿；Premiere FCP 7 XML、透明 PNG 字幕与 SRT。PR 输出是交换包，**不是原生 .prproj**；PNG 字幕可显示，但不是可编辑的原生字幕轨道。
- 精剪后合拢空隙：读取已保存的剪映草稿 / PR XML，生成新副本，共用视频时间映射移动字幕，保留短字幕相对片段的偏移。复杂转场、嵌套、变速等不支持结构会拒绝处理。
- 单击一键识别只做本地流程；AI 整句修正须人工复核后单独触发。
- 时间戳和声纹均需复核，英文词尾时间为估计值；噪声、重叠说话、口音可能降低准确率。没有宣称字幕与片段在编辑器内强制绑定。
- Windows x64 测试版，未代码签名；不包含 Adobe / 剪映软件，不保证其他剪映版本、CapCut 或所有 PR 工程兼容。

## 文件布局与隐私

`口播快剪.exe` 启动器、`runtime/` 程序依赖、`data/` 项目/模型/工具/缓存、`docs/` 教程与许可。复制整个文件夹可保留环境；分享前移除自己的 data 内容，遵守下载工具和模型的再分发许可。

本地 HTTP 服务只监听回环地址。素材不自动上传；点击 AI 操作时，会发送文稿、说话人标签及时间戳至你选择的 API 服务。API Key 仅存进程内存；不建立聊天历史，调用使用独立请求；供应商自身的数据保留政策由供应商决定。项目和文稿会保存在本地 data 中。详见 [隐私说明](docs/PRIVACY.md)。

## 从源码运行

Windows，Python 3.12：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python app.py --no-browser --port 8765
```

打开 `http://127.0.0.1:8765/`，英文入口加 `?lang=en`。开发环境 imageio-ffmpeg 的上游 wheel 自带媒体工具；公开应用包在用户首次使用时从上游校验下载。

```powershell
.\.venv\Scripts\python -m pytest tests -q
node --check static/app.js
node --check static/i18n.js
.\.venv\Scripts\python -m pip install pyinstaller==6.22.3
.\.venv\Scripts\python -m PyInstaller --noconfirm portable.spec
```

发布版组装和目录说明见 [维护指南](docs/RELEASING.md)。本项目源码 MIT；依赖和模型各自保留许可。见 [完整引用与许可](THIRD_PARTY_NOTICES.md)。
