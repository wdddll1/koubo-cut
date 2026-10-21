# 隐私 / Privacy

本地服务仅监听 127.0.0.1。无统计分析、遥测或自动素材上传。模型/工具下载会连接上游站点。点击 AI 功能时，文稿、时间戳、说话人标记会发送至配置的供应商；请只处理有权使用的内容。

API Key 不写入配置文件，只在当前服务进程内使用。请求是独立工具调用，不复用聊天记录；应用不能控制供应商的日志、缓存或留存政策。文稿、编辑决定和日志保存在 data，直到你自行清理；“无聊天记忆”不意味着本地项目不保存。

The server listens on loopback only, with no analytics, telemetry or automatic media uploads. Model/tool downloads contact upstream services. Explicit AI actions send transcript text, timestamps and speaker labels to the configured provider.

API keys are process-memory-only. Calls are independent tool requests without shared conversation history. Provider logging, caching and retention are outside this app's control. Local projects, transcripts, edit decisions and logs persist in data until you remove them. No chat memory does not mean no local project storage.
