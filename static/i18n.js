'use strict';
// UI-only translations. Transcript words, filenames and editable user text are
// deliberately excluded. Language also selects an isolated server workspace.
const KouboI18n=(()=>{
  const query=new URLSearchParams(location.search);
  let stored='zh';try{stored=localStorage.getItem('koubo-language')||'zh';}catch{}
  const language=(query.get('lang')||stored)==='en'?'en':'zh';
  const dictionary=Object.fromEntries(String.raw`
口播快剪 · 本地测试版 | Koubo Cut · Local beta
口播快剪 | Koubo Cut
你的工作台 | Your studio
导入口播视频 | Import video
最近的素材 | Recent media
回收站 | Recycle bin
本地处理 · 原片保留 | Local processing · Originals kept
模型与剪映设置 | Models & Jianying settings
让表达更紧凑， | Make every word count.
让剪辑决定留在你手里。 | Keep editing decisions in your hands.
工作台 | Studio
新建粗剪 | New rough cut
切换界面语言和识别模型 | Switch interface language and speech model
检查识别模型… | Checking speech model…
下载识别模型 | Download speech model
好内容，从剪掉多余开始。 | Great content. Fewer distractions.
识别中文口播，试听每一个切点，把确认后的方案带进剪映。 | Transcribe English speech, audition every cut, then continue in Jianying.
剪映 5.9 工作流 | Jianying 5.9 workflow
剪辑软件工作区 | Editing workspaces
识别 · 浓缩 · PR 工程交换包 | Transcribe · Condense · Premiere XML
进入 PR 区 ↗ | Open Premiere ↗
剪 | JY
剪映专业版 | Jianying Pro
保留现有剪映 5.9 工作流 | Jianying 5.9 draft workflow
进入剪映区 ↗ | Open Jianying ↗
工程制作功能后续开放 | Project export coming later
占位区 · 可提炼文稿 | Placeholder · Summaries available
AE 工程制作区 | After Effects workspace
这里先保留入口，暂不制作或导出 AE 工程。下方「AI 提炼主题与标题」可用于粘贴的文稿。 | AE project export is not implemented yet. You can summarize pasted text below.
精剪后合拢空隙 · 字幕同步 | Close gaps after fine editing · Keep subtitles in sync
已精剪工程路径 | Edited project path
填写本机完整路径 | Enter a full local path
合拢空隙并同步字幕 | Close gaps & sync subtitles
以所有剩余视频轨的实际画面区间为准，忽略黑色底板；请先删除各轨中不需要的画面。字幕和音频按同一时间映射平移，保留字幕在片段内的偏移，清除已删除画面区间的孤立字幕。请在添加转场、嵌套和跨空隙关键帧前合拢。原工程保留，输出新副本。 | All remaining picture tracks define retained time; the black base is ignored. Delete unwanted picture clips first. Audio and subtitles use the same time map, preserving subtitle offsets inside clips and removing orphaned subtitles. Close gaps before adding transitions, nested sequences or keyframes across gaps. A new copy is created.
AI 提炼主题与标题 | AI topic, summary & title
生成建议标题，提炼主要讲述内容、精简主体与关键要点，供修改和参考。不会改动剪辑方案。 | Generate a suggested title, main topic, concise summary and key points. Edit or copy the result; your cuts stay unchanged.
载入当前视频文稿 | Load current transcript
AI 提炼主题与标题 ✧ | Summarize & suggest title ✧
原文参考 · 可粘贴或修改 | Source text · Paste or edit
粘贴文稿，或载入当前视频的带人物标签文稿；最多 20,000 字符 | Paste a transcript or load the current one with speaker labels. Maximum 20,000 characters.
AI 反馈 · 可修改与复制 | AI result · Edit or copy
AI 反馈显示在这里，可直接修改；结果仅在当前页面保留 | Results appear here and can be edited. Results are kept only on this page.
复制反馈 | Copy result
导入视频 | Import video
识别与分析 | Transcribe & analyze
试听确认 | Review & audition
生成剪映草稿 | Create Jianying draft
选择或拖入视频 | Choose or drop a video
把你的口播原片放到这里 | Drop your original video here
拖入视频，或点击选择文件 | Drag a video here, or click to browse
大文件建议直接使用本机路径 | For large files, use a local path
例如 E:\视频素材\口播原片.mp4 | For example, D:\Videos\speech.mp4
导入原片 | Import source
选择文件会复制到工具数据目录；填写路径可直接引用原文件。 | Choosing a file copies it to app data; entering a path references the original file.
01 / 忠实转录 | 01 / Faithful transcripts
保留口误和重说，为删减提供依据。 | Keep false starts and repeated takes for review.
02 / 每一刀可确认 | 02 / Review every cut
建议默认待确认，可试听、撤销和微调。 | Audition, undo and fine-tune suggestions before applying them.
03 / 继续在剪映精修 | 03 / Continue in Jianying
生成引用原素材的独立草稿。 | Create a separate project referencing the source media.
原片时长 | Source duration
紧凑版预计 | Estimated compact cut
当前方案删减 | Time removed
尚未转录 | Not transcribed
开始中文转录 | Transcribe English
人物与对话 | Speakers & dialogue
尚未标记 | Not assigned
先转录，再运行本地声纹分组；A/B 是匿名人物标签，可选中文字修正。 | Transcribe first, then group voices locally. A/B are anonymous labels; select words to correct them.
说话人数 | Number of speakers
自动判断人数 | Detect automatically
已知双人对话 | Two speakers
已知单人口播 | One speaker
下载说话人模型 | Download speaker models
一键本地识别文稿与人物 | Transcribe & identify speakers locally
识别说话人 | Identify speakers
本地复核 → 上传 AI | Local review → Send to AI
先试听并修正人物，再调整分句。未上传时为本地临时分段；AI 按语义一句一拆，约9字供参考，可长可短。人工分句与合句会保留。 | Audition and correct speakers first, then adjust sentence boundaries. Local preview segments are provisional. AI splits natural short thoughts, roughly 6–12 English words; manual splits and joins are respected.
我已人工复核人物与分句，准备上传 AI | I reviewed speakers and sentence boundaries; ready to send to AI
原始文稿 | Transcript
待识别 | Awaiting transcription
人物 TXT ↗ | Speaker TXT ↗
文 | TXT
让原片变成可编辑的文字 | Turn speech into editable text
先完成本地转录，再选择文字试听或删除。 | Transcribe locally, then select words to audition or remove.
支持单人口播与双人对话，人物标签需试听复核。 | One-speaker and two-speaker workflows are supported. Review all speaker labels.
转录文稿 | Transcript
删除所选 | Remove selection
修正为人物 | Assign to speaker
人物 A | Speaker A
人物 B | Speaker B
不确定 | Unknown
修正人物 | Assign speaker
所选末尾分句 | Split after selection
取消该处分句 | Join at selection
取消 | Cancel
点击字词跳转试听；按住 Shift 点击结束字，可选择一段文字。 | Click a word to seek. Shift-click another word to select a range.
切点试听 | Audition cuts
原片 | Original
跳过当前删减方案 | Skip proposed deletions
从头试听 ↺ | Replay ↺
浏览器跳切用于快速试听。精确切点请结合渲染 MP4 与剪映检查。 | Browser seeking is a quick preview. Check precise cuts in the rendered MP4 and your editor.
原片编码可能不受浏览器支持。 | Your browser may not support the source codec.
生成兼容预览 | Create compatible preview
手动调整 | Manual adjustments
取当前时间 | Use playhead time
开始 / 秒 | Start / seconds
结束 / 秒 | End / seconds
分轨归类 | Track category
建议删除轨道 | Suggested deletion track
保留对话轨道（保护转场） | Keep dialogue / protect transition
无对话待审核轨道 | Non-dialogue review track
添加归类区间 | Add categorized range
取消紧凑删减 | Reset compact deletions
信息浓缩 | Content condensation
针对整个视频全部文稿，按有效文稿字数估算保留比例；优先保证核心意思与问答完整，实际值可能偏离目标。 | Apply the retention target to the entire transcript, estimated by content characters. Meaning and coherent dialogue take priority, so actual retention may differ.
启用 AI 信息浓缩 | Enable AI condensation
信息保留目标 | Target content retention
20% 最压缩 → 100% 不压缩 | 20% most condensed → 100% uncondensed
完成 AI 分析后显示实际比例。 | Actual retention appears after AI analysis.
独立工具请求：不保存聊天历史，不回传上轮回答。项目仅保存文稿、配置与剪辑决定；服务商缓存由服务商管理。 | Standalone tool requests: no chat history or previous responses are sent. Projects store transcripts, settings and edit decisions. Provider-side caching is controlled by the provider.
删减建议 | Deletion suggestions
分轨草稿会安放所有 AI 建议；勾选用于常规紧凑导出。直接删除模式使用整个建议删除轨道。可用分类菜单把转场改为保留。 | Review drafts include every suggestion. Check suggestions for normal compact export. Direct-delete mode removes the whole suggested-deletion track. Reclassify useful transitions as Keep.
全选 | Select all
取消全选 | Deselect all
重新生成规则建议 | Regenerate rule suggestions
上传 AI 拆句、校正与规划 | Send to AI: split, correct & plan
识别后进行 AI 整句校正；语气助词进入无内容轨道，浓缩时才按整句建议删减。 | After transcription, correct whole sentences with AI. Meaningless hesitation words go to the non-dialogue track; condensation selects whole sentences.
原时间轴 · 分轨审核 | Original timeline · Track review
每个时间点仅有一段原片；底层黑色铺满至结尾。点击片段可跳转试听。 | Source clips retain their original timing over a full-length black base. Click a clip to audition.
把分轨方案带到剪映 | Send the track plan to Jianying
分轨草稿保持原片时长与声音；紧凑版仅使用勾选的删减。字幕按原时间或紧凑时间自动匹配。 | Review drafts preserve timing and sound. Compact exports use checked deletions. Subtitles follow the corresponding timeline.
自动添加对应字幕（已按画面切点拆开，暂未启用删除联动） | Add matching subtitles (split at picture cuts; native delete-linking is not enabled)
剪映草稿名称 | Jianying draft name
留空按视频名称生成 | Leave blank to use the video name
按人工复核断句直接制作草稿（无需 AI） | Cut directly at manually reviewed sentence boundaries (no AI)
按当前文稿分句时间切开画面，保留人工删减与分轨，忽略自动 AI 建议。点击下方生成草稿／工程包。 | Cut using current reviewed sentence timestamps. Keep manual decisions and categories, ignoring automatic suggestions. Then create the project below.
直接删除建议轨道并合并剩余画面 | Delete the suggested-deletion track and join remaining clips
包含未勾选的 AI / 重复建议。保留保护转场与无对话待审核片段；仅影响新导出，原片不变。 | Includes unchecked AI / repeat suggestions. Protected transitions and non-dialogue review clips remain. Only the new export is affected.
草稿模式 | Draft mode
分轨审核 · 保留原时间轴 | Track review · Original timing
紧凑粗剪 · 按勾选缩短 | Compact cut · Checked deletions
分轨 JSON ↓ | Review JSON ↓
原时间 SRT ↓ | Original-time SRT ↓
紧凑 JSON ↓ | Compact JSON ↓
紧凑 SRT ↓ | Compact SRT ↓
渲染紧凑 MP4 | Render compact MP4
生成剪映草稿 ↗ | Create Jianying draft ↗
准备中 | Preparing
KOUBO CUT / 测试版 | KOUBO CUT / BETA
本地识别 · 人工确认 · 可编辑草稿 | Local transcription · Human review · Editable projects
关闭 | Close
识别在本机完成。点击 AI 分析时，仅将转录文字发送给所选服务商。 | Transcription runs locally. AI analysis sends transcript text only to the selected provider.
文本分析服务 | Text analysis provider
模型名称 | Model name
填写账户可用模型名 | Enter a model available to your account
仅保留在服务进程内存中，退出后需重新填写 | Kept in process memory only; enter again after restarting
清除当前内存中的 Key | Clear the in-memory API key
剪映 5.9 草稿文件夹 | Jianying 5.9 draft root
在剪映 设置 → 草稿位置 中查看 | Find this in Jianying Settings → Draft location
这里填写草稿目录，不是剪映程序目录。电脑上有多个版本时，请以 5.9 的设置为准。 | Enter the draft root, not the application directory. Use the location configured in Jianying 5.9.
PR 工程输出位于工具项目的 exports 文件夹，生成后可下载 ZIP。需另行安装 Adobe Premiere Pro。 | Premiere exports are stored in the project's exports folder and can be downloaded as ZIP. Install Premiere Pro separately.
长停顿阈值 / 毫秒 | Long-pause threshold / ms
缩短后保留 / 毫秒 | Retained pause / ms
整句模式不按短暂停顿生成删减建议；这些停顿参数仅供旧规则模式使用。 | Sentence mode does not cut short pauses automatically. These pause settings apply to legacy rule mode.
密钥不会写入项目文件或浏览器存储 | API keys are not written to projects or browser storage
保存设置 | Save settings
分析这份口播文稿 | Analyze this transcript
将字词 ID、转录文字和匿名人物标签发送给 | Send token IDs, transcript text and anonymous speaker labels to
，原视频和音频留在本机。请求会按你的 API 账户计费。 | . Original video and audio stay local. Your API account is billed by the provider.
先核对已人工复核的字词与人物，修复明显错字，仅添加引号、逗号、顿号；按语义一句一拆，约9字供参考，非强制限制，不把整个人的发言合为一句。保留人工指定的分句与合句。无意义语气助词单独进入无内容轨道。启用浓缩时，另一次独立请求综合全片所有句子选择可删除整句。原始时间与人物标签保持对应，不使用聊天记忆。请复核 AI 校正和切点。 | Review speakers and words first. AI fixes obvious errors, uses quotes and commas, and splits natural short thoughts (roughly 6–12 English words, not a strict limit). Manual splits and joins remain. Meaningless hesitation words go to the non-dialogue track. Condensation uses a separate request over all sentences. Timestamps and speaker labels stay attached; no chat history is used. Review corrections and cuts.
暂不分析 | Not now
发送文稿并分析 | Send transcript & analyze
模型与 PR 设置 | Models & Premiere settings
模型设置 | Model settings
已转录 | Transcribed
待转录 | Not transcribed
恢复 | Restore
● 中文识别模型已就绪 | ● English speech model ready
○ 首次使用需下载中文模型 | ○ Download the English model for first use
复用转录缓存 | Reuse transcript cache
本地预分段 · 待人工复核 | Local preview · Review required
先完成本地说话人识别，再上传 AI 校正 | Identify speakers locally before AI correction
自动分轨 | Automatic category
无内容轨道 | Non-dialogue track
保留对话轨道 | Keep dialogue track
手动删除 | Manual removal
AI 建议 | AI suggestion
相邻重复 | Adjacent repetition
长静音 | Long silence
语气助词 | Hesitation word
原片试听 | Audition source
跳过试听 | Audition cut
微调 | Fine-tune
移除 | Remove
黑色主轨道 | Black base
画中画0 · 保留对话 | Overlay 0 · Keep dialogue
画中画1 · 无内容与语气助词待审核 | Overlay 1 · Non-dialogue / hesitation review
画中画2 · 建议删除待审核 | Overlay 2 · Suggested deletion review
原时间轴 | Original timeline
候选原片试听 | Audition original range
跳过候选试听 | Audition without range
剪后试听 | Audition edited cut
请等待当前操作完成 | Wait for the current operation to finish
请等待当前任务完成 | Wait for the current task to finish
请先导入视频 | Import a video first
请先识别当前视频文稿 | Transcribe the current video first
请先粘贴或载入文稿 | Paste or load a transcript first
请先填写 API Key | Enter an API key in Settings first
处理完成，请试听确认 | Processing complete. Audition and review the result.
已复用转录缓存 | Reused the transcript cache
中文识别模型已准备完成 | English speech model is ready
说话人模型已就绪 | Speaker models are ready
原片已导入，下一步开始中文转录 | Source imported. You can now transcribe English speech.
视频已导入 | Video imported
读取视频并建立素材指纹 | Reading video and calculating its fingerprint
复制视频到本机数据目录，建立素材档案 | Copying media into the local data folder
切点试听结束 | Audition complete
这个区间没有可试听的相邻内容 | No adjacent content is available for audition
请点击视频播放按钮试听 | Click the video play button to audition
已移入工具回收站，原视频保留，可恢复 | Moved to the tool's recycle bin. The original video is kept and the project can be restored.
素材项目已恢复 | Media project restored
保存设置后即可使用 AI | Save settings to use AI
设置已保存；API Key 仅在当前服务内存保留 | Settings saved. The API key remains in this process's memory only.
已保存设置，API Key 不会写入磁盘 | Settings saved. The API key is not written to disk.
已设定人工分句，请重新确认复核 | Manual split saved. Confirm your review again.
已取消该处断句，请重新确认复核 | Sentence boundary removed. Confirm your review again.
已载入当前文稿，带匿名人物标签；可在左侧编辑后提交 | Transcript loaded with anonymous speaker labels. Edit it before sending.
尚无可复制的反馈 | No result to copy yet
已复制修改后的反馈 | Edited result copied
已选中反馈，请按 Ctrl+C 复制 | Result selected. Press Ctrl+C to copy.
当前文稿超过 20,000 字符，请分段粘贴后提炼 | The transcript exceeds 20,000 characters. Summarize shorter sections.
当前任务执行中，完成后可切换区块 | Finish the current task before switching workspaces
提炼文稿主题与标题 | Summarize topic & suggest title
将当前原文参考框中的文字发送给 | Send the text in the source box to
将转录字词 ID、原文和匿名人物标签发送给 | Send token IDs, source text and anonymous speaker labels to
请先完成本地说话人识别，再人工复核人物与分句 | Identify speakers locally, then review speakers and sentence boundaries
请先确认已人工复核人物与分句 | Confirm that you reviewed speakers and sentence boundaries
请先在设置中填写 API Key | Enter an API key in Settings first
不启用信息浓缩，普通内容整句保留。 | Condensation is disabled; regular sentences are retained.
目标已变更，请重新提交 AI 审核。 | The target changed. Run AI analysis again.
实际值偏离目标超过 10 个百分点，请复核或重新分析。 | Retention differs from the target by more than 10 percentage points. Review or analyze again.
目标为近似值，不强行删除关键信息。 | The target is approximate; essential information takes priority.
完成识别和分析后显示预计保留比例。 | Estimated retention appears after transcription and analysis.
直接删除整个建议删除轨道（包含未勾选建议），合拢剩余视频与字幕。JSON、SRT、MP4 和草稿使用同一时间映射。 | Delete the whole suggested-deletion track, including unchecked suggestions, and join remaining video and subtitles. JSON, SRT, MP4 and drafts share one time map.
分轨草稿保持原片位置与声音；常规紧凑导出只删除勾选区间。 | Review drafts preserve source timing and sound. Normal compact export removes checked ranges only.
直接使用当前人工复核分句时间戳切开画面，无需上传 AI；保留人工归类和删减，忽略自动建议。 | Cut at manually reviewed sentence timestamps without AI. Keep manual categories and deletions; ignore automatic suggestions.
生成 PR 合并工程包 ↗ | Create compact Premiere project ↗
生成 PR 工程包 ↗ | Create Premiere project ↗
生成合并草稿 ↗ | Create compact draft ↗
PR 2026 · 工程制作区 | Premiere 2026 · Project workspace
AE · 功能待开放 | AE · Coming later
识别中文口播，试听每一个切点，把确认后的方案带进 Premiere Pro。 | Transcribe English speech, audition every cut, then continue in Premiere Pro.
AE 工程功能预留；可先使用 AI 提炼主题整理文稿。 | AE project export is reserved for a future release. Summaries are available below.
03 / 继续在 PR 精修 | 03 / Continue in Premiere Pro
生成 PR 工程 | Create Premiere project
新建 PR 工程 | New Premiere project
AE 占位区 | AE placeholder
PR 工程名称 | Premiere project name
工程模式 | Project mode
把剪辑方案带到 Premiere Pro | Send the edit plan to Premiere Pro
精剪后保存的剪映草稿文件夹 | Saved, fine-edited Jianying draft folder
精剪后导出的 XML 完整路径 | Full path of XML exported after fine editing
在剪映保存并返回首页，填写精剪草稿文件夹或 draft_content.json 的路径。合拢后在首页刷新并打开名称含“精剪合拢”的新草稿。 | Save in Jianying and return to its home screen. Enter the draft folder or draft_content.json path. Refresh the home screen and open the new gap-closed copy.
在 PR 保存精剪结果，选中该序列 → 文件 → 导出 → Final Cut Pro XML。填写导出 XML 路径，合拢后导入新的 timeline.xml。支持本工具生成的透明图片字幕轨；PR 原生字幕轨需另行处理。 | Save your fine edit in Premiere. Select the sequence → File → Export → Final Cut Pro XML. Enter that XML path, close gaps, then import the new timeline.xml. Supports the tool's transparent-image subtitles; native Premiere caption tracks need separate handling.
请先填写已保存草稿或导出 XML 的本机路径 | Enter the local path of your saved draft or exported XML first
读取精剪工程，计算视频、音频和字幕的共同移动量… | Reading the edited project and calculating one time map for picture, audio and subtitles…
已生成精剪合拢副本 | Gap-closed copy created
下载合拢工程包 | Download gap-closed project
下载时间映射报告 | Download time-map report
精剪空隙已合拢，字幕按同一时间映射移动 | Gaps closed. Subtitles moved with the same time map.
已生成独立剪映草稿；在剪映首页刷新后打开“精剪合拢”副本。原草稿保留。 | A separate Jianying draft was created. Refresh Jianying's home screen and open the gap-closed copy. The original is kept.
在 PR 导入新 XML，打开“精剪合拢”序列。支持本工具的透明图片字幕轨；原序列保留。 | Import the new XML in Premiere and open the gap-closed sequence. Supports the tool's transparent-image subtitles; the original sequence is kept.
PR 输出 XML 工程交换包，切点按帧取整；导入后另存 .prproj。勾选字幕会添加独立透明字幕画面轨，导入即显示；改字可使用同包 SRT，字幕未启用删除联动。 | Premiere exports use frame-aligned XML. Import and save as .prproj. Subtitles are transparent-image clips on a separate track; use the included SRT to recreate editable captions. Native delete-linking is not enabled.
已启用删除建议轨道并合并。 | Suggested-deletion removal and compaction enabled.
默认保留完整分轨供审核。 | Full review tracks are retained by default.
请求失败 | Request failed
操作失败，请检查文件格式或重新启动。原视频不会被修改。 | Operation failed. Check the file format or restart the tool. Original videos are unchanged.
请先完成中文转录 | Transcribe English speech first
请先完成中文转录或一键本地识别 | Transcribe English speech or run local preparation first
中文识别模型尚未准备，请先点击「下载识别模型」 | Download the English speech model first
请先完成文稿与人物识别 | Transcribe and identify speakers first
请先完成本地说话人识别，并确认已人工复核人物与分句 | Identify speakers locally and confirm you reviewed speakers and sentence boundaries
原视频已移动或删除，请重新导入相同文件 | Source media was moved or removed. Import the same file again.
项目有任务正在运行，请等待完成 | This project has a running task. Wait for it to finish.
找不到项目 | Project not found
模型正在下载 | A model download is already running
未识别到语音，请检查音轨、音量和素材语言 | No speech detected. Check the audio track, volume and selected language.
AI 返回的 JSON 不完整，未应用任何建议 | AI returned incomplete JSON. No suggestions were applied.
模型返回的 JSON 不完整，未应用任何建议 | The model returned incomplete JSON. No suggestions were applied.
模型请求超时；原剪辑方案未修改，请稍后重试 | AI request timed out. Your edit plan is unchanged; retry later.
无法连接模型服务，请检查网络；原剪辑方案未修改 | Cannot reach the AI provider. Check your network; the edit plan is unchanged.
AI 句子遗漏原文，未应用 | AI sentences omitted source words. No changes were applied.
AI 将不同人物发言合为一句，未应用 | AI merged different speakers into one sentence. No changes were applied.
AI 未遵守人工分句或合句，整次结果未应用 | AI did not respect manual sentence boundaries. No changes were applied.
AI 将非语气助词标为无内容，未应用 | AI marked meaningful words as hesitation. No changes were applied.
AI 添加了引号、逗号、顿号以外的符号，未应用 | AI added unsupported punctuation. No changes were applied.
AI 校正格式无效，整次结果未应用 | Invalid AI correction format. No changes were applied.
请确认将转录文字发送给所选模型服务商 | Confirm sending the transcript to the selected AI provider
当前方案已变化，请重新确认后重试 | The edit plan changed. Review it again and retry.
未填写 | Not set
已在内存中设置 | Set in memory
待定 | Unknown
无内容 | Non-dialogue
无对话 | No dialogue
保留 | Keep
建议删除 | Suggested deletion
人工选择文稿区间 | Manually selected transcript range
可能是强调，请确认 | This may be emphasis; please review
检测到较长静音，建议缩短；请试听确认 | A long silence was detected. Audition before shortening it.
相邻内容完全重复，建议删除第一次；可能是强调，请确认 | Exact adjacent repetition. Consider removing the first take; review for intentional emphasis.
读取识别用音频 | Reading analysis audio
提取识别用音频 | Extracting analysis audio
检测静音 | Detecting silence
校验原视频指纹 | Verifying source fingerprint
AI 校正全文、识别完整句子与无意义语气助词 | AI: correcting sentences and identifying meaningless hesitation words
AI 综合整段视频全部句子进行信息浓缩 | AI: condensing all sentences across the full video
AI 提炼主题与精简主体（独立请求） | AI: summarizing the topic (standalone request)
正在生成剪映草稿 | Creating Jianying draft
正在生成 PR 工程 | Creating Premiere project
已完成 | Complete
文稿 · | Transcript ·
人物 · | Speakers ·
识别模型 · | Speech model ·
人物模型 · | Speaker model ·
语音检测与人物聚类 | Speech detection & speaker clustering
移除最近素材，原视频保留 | Remove recent media; keep the original video
暂无删除建议。可进行 AI 分析，或选择文字手动剪辑。 | No deletion suggestions. Analyze with AI or select words to edit manually.
画中画0 · 保留 | Overlay 0 · Keep
画中画1 · 无内容 | Overlay 1 · Non-dialogue
画中画2 · 建议删除 | Overlay 2 · Suggested deletion
主轨道 · 黑色 | Main track · Black base
秒 | seconds
例如 D:\JianyingPro Drafts\我的精剪草稿 | Example: D:\JianyingPro Drafts\My reviewed draft
例如 D:\精剪工程\精剪序列.xml | Example: D:\Edited projects\Sequence.xml
准备说话人模型 | Preparing speaker models
加载说话人分离模型 | Loading diarization models
声纹提取与分组 | Extracting and grouping voices
浏览器无法连接本地服务 | Cannot connect to the local service
`.trim().split('\n').map(line=>{const n=line.indexOf(' | ');return[line.slice(0,n),line.slice(n+3)];}));
  const patterns=[
    [/^原时长 (.+) · (\d+) 段$/,m=>`Source duration ${m[1]} · ${m[2]} clips`],
    [/^回收站（(\d+)）$/,m=>`Recycle bin (${m[1]})`],
    [/^(.+) · 已转录$/,m=>`${m[1]} · Transcribed`], [/^(.+) · 待转录$/,m=>`${m[1]} · Not transcribed`],
    [/^整句 (\d+) 段 · 校正 (\d+) 处$/,m=>`${m[1]} sentences · ${m[2]} corrections`],
    [/^(\d+) 组声纹 · 待复核$/,m=>`${m[1]} voice groups · Review required`],
    [/^(\d+) 个字词 · (\d+) 项已确认$/,m=>`${m[1]} words · ${m[2]} accepted suggestions`],
    [/^已选 (\d+) 个字词 · (.+)$/,m=>`Selected ${m[1]} words · ${m[2]}`],
    [/^人物 (.+)$/,m=>`Speaker ${m[1]}`], [/^至 (.+)$/,m=>`to ${m[1]}`],
    [/^合拢 (\d+) 处空隙，缩短 (.+) 秒；结果时长 (.+) 秒。$/,m=>`Closed ${m[1]} gaps, removed ${m[2]} seconds; result: ${m[3]} seconds.`],
    [/^已生成 PR 工程交换包 · (\d+) 个片段$/,m=>`Premiere XML created · ${m[1]} clips`],
    [/^文稿与人物识别完成：(\d+) 组声纹，请复核$/,m=>`Transcript ready with ${m[1]} voice groups. Review the labels.`],
    [/^识别到 (\d+) 组声纹，请复核 A\/B 标签$/,m=>`${m[1]} voice groups detected. Review A/B labels.`],
    [/^整句 (\d+) 段，校正 (\d+) 处，语气助词 (\d+) 段；请试听复核$/,m=>`${m[1]} sentences, ${m[2]} corrections, ${m[3]} hesitation ranges. Audition and review.`],
    [/^随后综合整段视频全部文稿，目标保留约 (\d+)%[。]?$/,m=>`Then analyze the entire transcript, targeting about ${m[1]}% retention.`],
    [/^本次提交 (\d+) 字符；返回建议标题、主题、精简主体与要点，不修改剪辑。$/,m=>`Send ${m[1]} characters. Return title, topic, summary and key points; cuts stay unchanged.`],
    [/^无法连接本地服务：(.+)$/,m=>`Cannot connect to local service: ${m[1]}`],
    [/^模型服务返回 HTTP (\d+)，请检查 Key、余额和模型名$/,m=>`AI provider returned HTTP ${m[1]}. Check your key, credits and model name.`],
    [/^移除 (.+)$/,m=>`Remove ${m[1]}`],
    [/^整段视频预计保留文稿 (.+)%（(.+)\/(.+) 字）；(.+)$/,m=>`Estimated retention: ${m[1]}% (${m[2]}/${m[3]} content characters). ${translate(m[4])}`],
    [/^识别第 (\d+)\/(\d+) 段$/,m=>`Transcribing chunk ${m[1]}/${m[2]}`]
  ];
  function translate(text){
    if(language!=='en'||!/[\u3400-\u9fff]/.test(text))return text;
    const value=text.trim();
    if(dictionary[value])return text.replace(value,dictionary[value]);
    for(const [pattern,render] of patterns){const match=value.match(pattern);if(match)return render(match);}
    // Composite UI strings preserve numbers, timing and markup-created fragments.
    let result=text;
    for(const [a,b] of Object.entries(dictionary).sort((a,b)=>b[0].length-a[0].length)){
      if(a.length>2&&result.includes(a))result=result.split(a).join(b);
    }
    return result;
  }
  function apply(root){
    if(language!=='en')return;
    if(root.nodeType===Node.TEXT_NODE){
      if(root.parentElement?.closest('textarea,script,style,.token,.project-item strong,.trash-row span,#project-name,[data-i18n-skip]'))return;
      if(/^[A-Za-z]:[\\/]/.test(root.textContent.trim()))return;
      const value=translate(root.textContent);if(value!==root.textContent)root.textContent=value;return;
    }
    if(root.nodeType!==Node.ELEMENT_NODE)return;
    if(root.matches('script,style,[data-i18n-skip]'))return;
    for(const name of ['title','placeholder','aria-label']){
      const value=root.getAttribute(name);if(value){const next=translate(value);if(next!==value)root.setAttribute(name,next);}
    }
    if(root.matches('textarea,.token'))return;
    for(const child of root.childNodes)apply(child);
  }
  function start(){
    document.documentElement.lang=language==='en'?'en':'zh-CN';
    if(language==='en'){
      apply(document.documentElement);
      const observer=new MutationObserver(records=>{
        for(const record of records){if(record.type==='characterData')apply(record.target);else if(record.type==='attributes')apply(record.target);else for(const node of record.addedNodes)apply(node);}
      });
      observer.observe(document.documentElement,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['title','placeholder','aria-label']});
    }
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
  return {language,translate,dictionary};
})();
