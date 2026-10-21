import copy
import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from download_model import MODEL_ID, download_model
from . import ai, media, speakers, editorial, english
from .sentences import preview_breaks
from .premiere import export_premiere
from .core import compile_plan, interval, make_candidate, rule_candidates, srt_text, subtitle_cues, validate_tokens
from .draft import export_draft
from .review import compile_review_plan, review_subtitles
from .workflow import compact_plan, retention_report, validate_options


def save_json(path, data):
    temporary = Path(str(path) + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def invalidate_semantic_suggestions(project):
    kept = []
    for candidate in project['candidates']:
        if candidate['kind'] in ('ai', 'repeat'):
            if candidate.get('review_action', 'auto') == 'auto':
                continue
            candidate['kind'] = 'manual'  # retain a user's explicit track choice
        kept.append(candidate)
    project['candidates'] = kept


class Service:
    def __init__(self, directory, target="jianying", shared=None, language='zh'):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / "projects").mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.jobs = {}
        self.model_lock = shared.model_lock if shared else threading.Lock()
        self.target = target
        self.language = language
        self.model_root = shared.model_root if shared else self.directory / "models"
        self.settings_directory = shared.settings_directory if shared else self.directory
        self.portable = (self.settings_directory / 'portable.json').is_file()
        self.settings = {"provider": "deepseek", "model": "deepseek-chat", "api_key": "",
                         "draft_root": "", "silence_threshold": 900, "silence_keep": 320}
        path = self.settings_directory / "settings.json"
        if path.exists():
            known = json.loads(path.read_text(encoding="utf-8"))
            self.settings.update({key: value for key, value in known.items() if key in self.settings and key != "api_key"})

        if self.portable:
            relative = self.settings.get('draft_root', '')
            if relative and not Path(relative).is_absolute():
                self.settings['draft_root'] = str((self.settings_directory / relative).resolve())

        if shared:
            self.settings = shared.settings
            self.lock = shared.lock

    @property
    def model_dir(self):
        return self.model_root / (english.MODEL_ID if self.language=='en' else MODEL_ID)

    def model_ready(self):
        return english.ready(self.model_dir) if self.language=='en' else (self.model_dir/'model.int8.onnx').is_file()

    def download_speech_model(self, progress):
        return english.download(self.model_dir,progress) if self.language=='en' else download_model(self.model_dir,progress)

    def status(self):
        with self.lock:
            settings = {k: v for k, v in self.settings.items() if k != "api_key"}
            settings["has_api_key"] = bool(self.settings["api_key"])
            projects = []
            for path in sorted((self.directory / "projects").glob("*/project.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    project = json.loads(path.read_text(encoding="utf-8"))
                    projects.append({"id": project["id"], "name": project["media"]["name"],
                                     "duration": project["media"]["duration"], "transcribed": bool(project.get("transcript"))})
                except (ValueError, OSError, KeyError):
                    continue
            archived=[]
            for path in (self.directory/'trash').glob('*/project.json'):
                try:
                    if not re.fullmatch(r'[a-f0-9]{16}-[a-f0-9]{32}',path.parent.name):continue
                    item=json.loads(path.read_text(encoding='utf-8'))
                    archived.append({'id':item['id'],'name':item['media']['name'],'archive_id':path.parent.name})
                except (ValueError,OSError,KeyError):continue
            return {"archived_projects":archived,"version": "0.6.0-beta.1", "language":self.language, "app_root": str(Path(__file__).resolve().parents[1]),
                    "workspace": self.target, "premiere_installed": any((Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Adobe').glob('Adobe Premiere Pro */Adobe Premiere Pro.exe')),
                    "process_id": os.getpid(), "settings": settings, "projects": projects,
                    "active_jobs": [{k:j[k] for k in ("action", "project_id", "progress")} for j in self.jobs.values() if j["status"] == "running"],
                    "model_ready": self.model_ready(),
                    'speaker_model_ready': speakers.ready(self.model_root/'speakers'),
                    "data_directory": str(self.directory), "draft_suggestions": self.draft_suggestions()}

    def draft_suggestions(self):
        paths = []
        config = Path(os.environ.get("LOCALAPPDATA", "")) / "JianyingPro/User Data/Config/globalSetting"
        if config.is_file():
            match = re.search(r"^currentCustomDraftPath=(.+)$", config.read_text(encoding="utf-8", errors="replace"), re.MULTILINE)
            if match:
                candidate = match.group(1).strip().replace("\\\\", "\\")
                if Path(candidate).is_dir():
                    paths.append(candidate)
        default = Path(os.environ.get("LOCALAPPDATA", "")) / "JianyingPro/User Data/Projects/com.lveditor.draft"
        if default.is_dir():
            paths.append(str(default))
        return list(dict.fromkeys(paths))

    def configure(self, data):
        with self.lock:
            provider = data.get("provider", self.settings["provider"])
            if provider not in ("deepseek", "openai"):
                raise ValueError("模型服务商必须是 DeepSeek 或 OpenAI")
            model = str(data.get("model", self.settings["model"])).strip()
            if not model or len(model) > 150:
                raise ValueError("请填写模型名称")
            threshold = data.get("silence_threshold", self.settings["silence_threshold"])
            keep = data.get("silence_keep", self.settings["silence_keep"])
            rule_candidates({"media": {"duration": 1000}}, threshold, keep)
            changed_provider = provider != self.settings["provider"]
            self.settings.update({"provider": provider, "model": model,
                                  "draft_root": str(data.get("draft_root", self.settings["draft_root"])).strip().strip('"'),
                                  "silence_threshold": threshold, "silence_keep": keep})
            if changed_provider:
                self.settings["api_key"] = ""
            if data.get("clear_key"):
                self.settings["api_key"] = ""
            elif data.get("api_key"):
                key = str(data["api_key"]).strip()
                if len(key) > 1000 or "\n" in key or "\r" in key:
                    raise ValueError("API Key 格式错误")
                self.settings["api_key"] = key
            saved = {k: v for k, v in self.settings.items() if k != "api_key"}
            if self.portable and saved['draft_root']:
                root = Path(saved['draft_root']).resolve()
                if root.is_relative_to(self.settings_directory):
                    saved['draft_root'] = root.relative_to(self.settings_directory).as_posix()
            save_json(self.settings_directory / "settings.json", saved)
        return self.status()

    def project_dir(self, project_id):
        if not re.fullmatch(r"[a-f0-9]{16}", project_id):
            raise ValueError("项目 ID 无效")
        return self.directory / "projects" / project_id

    def load(self, project_id):
        path = self.project_dir(project_id) / "project.json"
        if not path.exists():
            raise ValueError("找不到项目")
        project = json.loads(path.read_text(encoding="utf-8"))
        if self.portable and project.get('source_relative'):
            source = (self.settings_directory / project['source_relative']).resolve()
            if not source.is_relative_to(self.settings_directory):
                raise ValueError('便携素材路径超出数据目录')
            project['source_path'] = str(source)
        if 'editing_policy' not in project:
            project['editing_policy'] = 'sentences'
            project['candidates'] = [c for c in project.get('candidates',[]) if c['kind']=='manual' or c.get('review_action','auto')!='auto' or c.get('accepted')]
        if project.get('editorial') and project['editorial'].get('sentence_policy_version')!=2:
            editorial.invalidate(project)
            project.update(subtitle_breaks=[],review_confirmed=False)
        return project

    def persist(self, project):
        if self.portable:
            source = Path(project['source_path']).resolve()
            if not source.is_relative_to(self.settings_directory):
                raise ValueError('便携版素材必须保存在数据目录内，请重新导入素材')
            project['source_relative'] = source.relative_to(self.settings_directory).as_posix()
        save_json(self.project_dir(project["id"]) / "project.json", project)

    def ensure_idle(self, project_id):
        if any(j["project_id"] == project_id and j["status"] == "running" for j in self.jobs.values()):
            raise ValueError("项目有任务正在运行，请等待完成")

    def view(self, project_id):
        with self.lock:
            project = self.load(project_id)
            return {**project, "preview_breaks":preview_breaks(project), "plan": compact_plan(project), 'review_plan':compile_review_plan(project), 'retention_report':retention_report(project)}

    def import_video(self, path):
        path = str(Path(str(path).strip().strip('"')).resolve(strict=True))
        info = media.inspect_video(path)
        digest = media.source_hash(path)
        if self.portable and not Path(path).is_relative_to(self.settings_directory):
            uploads = self.settings_directory / 'uploads'
            uploads.mkdir(exist_ok=True)
            copied = uploads / (digest + Path(path).suffix.lower())
            if not copied.is_file() or media.source_hash(copied) != digest:
                temporary = copied.with_suffix(copied.suffix + '.copying')
                shutil.copy2(path, temporary)
                if media.source_hash(temporary) != digest:
                    raise ValueError('素材复制校验失败，请重新导入')
                os.replace(temporary, copied)
            path = str(copied)
        project_id = digest[:16]
        with self.lock:
            target = self.project_dir(project_id)
            target.mkdir(exist_ok=True)
            if (target / "project.json").exists():
                self.ensure_idle(project_id)
                project = self.load(project_id)
                # Relinking identical bytes is safe; timing references remain unchanged.
                project["source_path"] = path
                project["media"]["name"] = info["name"]
            else:
                project = {"id": project_id, "source_id": digest, "source_path": path, "media": info, 'language':self.language,
                           "created_at": time.time(), "transcript": {}, "silences": [], "candidates": [],
                           "edits_version": 0, "warnings": [], "editing_policy":"sentences"}
                if info["audio_tracks"] > 1:
                    project["warnings"].append("检测到多音轨：测试版仅分析和预览第一音轨，请在剪映内确认原片声音。")
                if str(info.get("frame_rate_mode", "")).upper() == "VFR":
                    project["warnings"].append("素材为可变帧率；请在剪映中重点检查切点与音画同步。")
            self.persist(project)
        return self.view(project_id)

    def archive_project(self, project_id, restore=False, archive_id=None):
        with self.lock:
            self.ensure_idle(project_id)
            projects=(self.directory/'projects').resolve()
            trash=(self.directory/'trash').resolve()
            active=self.project_dir(project_id).resolve()
            if projects.parent!=self.directory or trash.parent!=self.directory or active.parent!=projects or active.is_symlink():raise ValueError('项目目录不安全')
            trash.mkdir(exist_ok=True)
            if restore:
                if not isinstance(archive_id,str) or not re.fullmatch(project_id+r'-[a-f0-9]{32}',archive_id):raise ValueError('恢复标识无效')
                archived=(trash/archive_id).resolve()
                if archived.parent!=trash or not archived.is_dir() or active.exists():raise ValueError('无法恢复：项目不存在或已重新导入')
                archived.rename(active)
                return {'id':project_id,'restored':True}
            self.load(project_id)
            if not active.is_dir():raise ValueError('项目不存在')
            archive_id=project_id+'-'+uuid.uuid4().hex
            target=(trash/archive_id).resolve()
            if target.parent!=trash or target.exists():raise ValueError('回收站目标无效')
            active.rename(target)
            return {'id':project_id,'archive_id':archive_id,'archived':True}

    def start_job(self, action, project_id=None, options=None):
        options = options or {}
        with self.lock:
            if action in ("download_model", 'download_speakers', 'summarize'):
                if any(j["action"] == action and j["status"] == "running" for j in self.jobs.values()):
                    raise ValueError("模型正在下载")
            else:
                self.load(project_id)
                self.ensure_idle(project_id)
            key = uuid.uuid4().hex
            self.jobs[key] = {"id": key, "action": action, "project_id": project_id, "status": "running",
                              "message": "准备中", "progress": 0, "result": None}
            settings = dict(self.settings)
        def progress(message, percent):
            with self.lock:
                self.jobs[key].update(message=message, progress=percent)
        def work():
            try:
                result = self.execute(action, project_id, options, settings, progress)
                with self.lock:
                    self.jobs[key].update(status="done", message="已完成", progress=100, result=result)
            except Exception as error:
                # Do not log stack traces with request payloads or credentials.
                message = str(error).replace(settings.get("api_key") or "\0", "[hidden]")[:2200]
                with self.lock:
                    self.jobs[key].update(status="error", message=message)
        threading.Thread(target=work, daemon=True).start()
        return {"job_id": key}

    def execute(self, action, project_id, options, settings, progress):
        settings = {**settings, 'language': self.language}
        if action == 'summarize':
            if options.get('consent') is not True:
                raise ValueError('请确认将本次文稿发送至 AI')
            progress('AI 提炼主题与精简主体（独立请求）', 10)
            return ai.summarize(options.get('text'), settings)
        if action == "download_model":
            with self.model_lock:
                self.download_speech_model(progress)
            return {"model_ready": True}
        if action == 'download_speakers':
            with self.model_lock:
                speakers.download(self.model_root/'speakers', progress)
            return {'speaker_model_ready':True}
        project = self.load(project_id)
        directory = self.project_dir(project_id)
        source = Path(project["source_path"])
        if not source.is_file():
            raise ValueError("原视频已移动或删除，请重新导入相同文件")
        if source.stat().st_size != project["media"]["bytes"]:
            raise ValueError("原视频发生变化，请重新导入")
        if action in ("draft", "premiere", "render", "transcribe", "proxy", 'diarize'):
            progress("校验原视频指纹", 0)
            if media.source_hash(source) != project["source_id"]:
                raise ValueError("原视频内容已改变，请重新导入")
        if action == 'prepare_editorial':
            raise ValueError('一键功能现仅本地识别，请完成人工复核后单独提交 AI 校正')
        if action == 'prepare':
            count = options.get('speakers', -1)
            validate_options({'speakers': count})
            with self.model_lock:
                if not self.model_ready():
                    self.download_speech_model(lambda m,p: progress('识别模型 · '+m, round(p*.15)))
                if not speakers.ready(self.model_root/'speakers'):
                    speakers.download(self.model_root/'speakers', lambda m,p: progress('人物模型 · '+m, round(15+p*.15)))
            self.execute('transcribe', project_id, {}, settings, lambda m,p: progress('文稿 · '+m, round(30+p*.45)))
            current = self.load(project_id)
            if current.get('diarization', {}).get('status') == 'done' and current['diarization'].get('requested_speakers') == count:
                return {'speaker_count': current['diarization']['speaker_count'], 'cached': True}
            return self.execute('diarize', project_id, {'speakers':count}, settings, lambda m,p: progress('人物 · '+m, round(75+p*.25)))
        if action == "transcribe":
            if project.get("transcript") and not options.get("force"):
                return {"cached": True, "message": "已复用转录缓存"}
            progress("提取识别用音频", 1)
            audio = media.prepare_audio(source, directory)
            progress("检测静音", 3)
            silences = media.detect_silence(audio, project["media"]["duration"])
            transcribe = english.transcribe if self.language=='en' else media.transcribe
            transcript = transcribe(audio, project["media"], silences, self.model_dir, progress)
            validate_tokens(transcript["tokens"], project["media"]["duration"])
            editorial.invalidate(project)
            project.update(manual_breaks=[],manual_joins=[],review_confirmed=False)
            project.update(transcript=transcript, silences=silences, diarization={}, subtitle_breaks=[])
            project["candidates"] = [] if project.get("editing_policy")=="sentences" else rule_candidates(project, settings["silence_threshold"], settings["silence_keep"])
            project["edits_version"] += 1
            with self.lock:
                self.persist(project)
            save_json(directory / "transcript.json", transcript)
            save_json(directory / "silence.json", silences)
            (directory / "transcript.txt").write_text("\n".join(s["text"] for s in transcript["segments"]), encoding="utf-8")
            return {"tokens": len(transcript["tokens"]), "candidates": len(project["candidates"])}
        if action == 'diarize':
            if not project.get('transcript'):
                raise ValueError('请先完成中文转录')
            count = options.get('speakers', -1)
            if isinstance(count, bool) or count not in (-1, 1, 2):
                raise ValueError('人物数量仅支持自动、1 人或 2 人')
            audio = media.prepare_audio(source, directory)
            result = speakers.diarize(audio, project['media']['duration'], self.model_root/'speakers', count, progress)
            speakers.assign_tokens(project['transcript']['tokens'], result['segments'])
            project['diarization'] = result
            # Suggestions made before speaker labels may mistake a reply for repetition.
            editorial.invalidate(project)
            project['review_confirmed']=False
            invalidate_semantic_suggestions(project)
            if project.get('editing_policy')!='sentences':
                project['candidates'] += [c for c in rule_candidates(project, settings['silence_threshold'], settings['silence_keep']) if c['kind']=='repeat']
            project['subtitle_breaks'] = []
            project['edits_version'] += 1
            with self.lock:
                self.persist(project)
            save_json(directory/'transcript.json', project['transcript'])
            save_json(directory/'speakers.json', result)
            return {'speaker_count':result['speaker_count']}
        if action == "rules":
            if not project.get("transcript"):
                raise ValueError("请先完成转录")
            if project.get("editing_policy")=="sentences":
                return {"candidates":0,"message":"整句模式不生成重复或短暂停顿切片，请使用 AI 校正文稿"}
            previous = {c["id"]: c for c in project["candidates"]}
            generated = rule_candidates(project, settings["silence_threshold"], settings["silence_keep"])
            for candidate in generated:
                if candidate["id"] in previous and all(previous[candidate["id"]][k] == candidate[k] for k in ("start", "end")):
                    candidate["accepted"] = previous[candidate["id"]]["accepted"]
                    candidate['review_action'] = previous[candidate['id']].get('review_action', 'auto')
            project["candidates"] = [c for c in project["candidates"] if c["kind"] not in ("repeat", "silence")] + generated
            project["edits_version"] += 1
            with self.lock:
                self.persist(project)
            return {"candidates": len(generated)}
        if action == "analyze":
            if options.get("consent") is not True:
                raise ValueError("请确认将转录文字发送给所选模型服务商")
            if project.get('editing_policy')=='sentences' and (project.get('diarization',{}).get('status')!='done' or project.get('review_confirmed') is not True):
                raise ValueError('请先完成本地说话人识别，并确认已人工复核人物与分句')
            analysis = editorial.analyze(project, settings, progress) if project.get('editing_policy')=='sentences' else ai.analyze(project, settings, progress)
            candidates = analysis['candidates']
            previous = {c["id"]: c for c in project["candidates"]}
            for candidate in candidates:
                if candidate["id"] in previous and all(previous[candidate["id"]][k] == candidate[k] for k in ("start", "end")):
                    candidate["accepted"] = previous[candidate["id"]]["accepted"]
                    candidate['review_action'] = previous[candidate['id']].get('review_action', 'auto')
            preserved = [c for c in project['candidates'] if c['kind']=='manual' or c.get('review_action','auto')!='auto' or c.get('accepted')]
            project['candidates'] = list({c['id']:c for c in preserved+candidates}.values())
            if project.get('editing_policy')=='sentences':
                project['editorial'] = {k:v for k,v in analysis.items() if k!='candidates'}
                for t in project['transcript']['tokens']:
                    t.pop('corrected_text',None)
                    if t['id'] in analysis['corrections']:t['corrected_text']=analysis['corrections'][t['id']]
                project['subtitle_breaks']=[s['to_token'] for s in analysis['sentences']]
            else:
                project['subtitle_breaks'] = analysis['subtitle_breaks']
            compact_plan(project)  # Validate direct-delete output before committing any AI results.
            project['ai_analysis'] = {'compression_enabled': project.get('workflow', {}).get('compression_enabled', False), 'retention': project.get('workflow', {}).get('retention', 70), 'completed_at': time.time(), 'stateless': True}
            project["edits_version"] += 1
            with self.lock:
                self.persist(project)
            return {"candidates": len(candidates), 'sentences':len(analysis.get('sentences',[])), 'corrections':len(analysis.get('corrections',{})), 'fillers':len(analysis.get('fillers',[]))}
        if action == "proxy":
            progress("转码浏览器兼容预览（不改变原片）", 10)
            media.create_proxy(source, directory / "proxy.mp4")
            return {"url": f"/media/{project_id}/proxy.mp4"}
        plan = compact_plan(project)
        # Exports use immutable snapshots; editing is blocked for the job duration.
        save_json(directory / "edit_plan.json", plan)
        (directory / "subtitles.srt").write_text(srt_text(subtitle_cues(project, plan)), encoding="utf-8-sig")
        if action == 'premiere':
            if self.target != 'pr':
                raise ValueError('请在 PR 区生成 PR 工程交换包')
            mode = 'compact' if project.get('workflow', {}).get('direct_delete') else options.get('mode', 'review')
            if mode not in ('review','compact'):
                raise ValueError('无效的 PR 工程模式')
            if mode == 'review':
                plan = compile_review_plan(project)
            progress('生成 PR 帧级时间轴、音频链接与字幕', 30)
            result = export_premiere(project, plan, directory, options.get('subtitles', True) is True, mode)
            save_json(directory/'premiere-manifest.json', {'edits_version':project['edits_version']})
            result['url'] = f'/download/{project_id}/premiere.zip?workspace=pr'
            return result
        if action == "draft":
            if self.target != "jianying":
                raise ValueError("请在剪映区生成剪映草稿")
            root = str(options.get("root") or settings["draft_root"]).strip().strip('"')
            if not root or not Path(root).is_absolute():
                raise ValueError("请在设置中填写剪映草稿文件夹的绝对路径")
            progress("生成剪映 5.9 新草稿", 30)
            mode = 'compact' if project.get('workflow', {}).get('direct_delete') else options.get('mode', 'review')
            if mode not in ('review', 'compact'):
                raise ValueError('无效的草稿模式')
            if mode == 'review':
                plan = compile_review_plan(project)
                save_json(directory/'review_plan.json', plan)
            return export_draft(project, plan, root, options.get("subtitles", True) is True, mode, project.get('workflow', {}).get('draft_name', ''))
        if action == "render":
            media.render_video(source, plan, directory / "edited.mp4", directory, progress)
            save_json(directory / "edited-manifest.json", {"edits_version": project["edits_version"], "output_duration": plan["output_duration"]})
            return {"url": f"/media/{project_id}/edited.mp4", "path": str(directory / "edited.mp4")}
        raise ValueError("未知任务")

    def update_candidates(self, project_id, data):
        with self.lock:
            self.ensure_idle(project_id)
            project = self.load(project_id)
            if data.get("edits_version") != project["edits_version"]:
                raise ValueError("页面方案已过期，请刷新项目后重试")
            action = data.get("action")
            if action == 'config':
                project['workflow'] = validate_options({**project.get('workflow', {}), **data.get('config', {})})
            elif action == 'select_all':
                if not isinstance(data.get('accepted'), bool):
                    raise ValueError('确认状态必须为布尔值')
                for candidate in project['candidates']:
                    candidate['accepted'] = data['accepted'] and candidate.get('review_action') not in ('keep', 'no_dialogue') and candidate['kind']!='filler'
            elif action == "add":
                start, end = interval(data.get("start"), data.get("end"), project["media"]["duration"])
                reason = str(data.get("reason", "手动选择删除"))[:500]
                candidate = make_candidate("manual", start, end, reason, str(data.get("text", "手动区间"))[:500])
                category = data.get('review_action', 'delete')
                if category not in ('keep','no_dialogue','delete'):
                    raise ValueError('无效的分轨分类')
                candidate['review_action'] = category
                candidate["accepted"] = category == 'delete'
                project["candidates"] = [c for c in project["candidates"] if c["id"] != candidate["id"]] + [candidate]
            elif action == 'confirm_review':
                if type(data.get('confirmed')) is not bool:raise ValueError('复核状态无效')
                if project.get('diarization',{}).get('status')!='done':raise ValueError('请先完成本地说话人识别')
                project['review_confirmed']=data['confirmed']
            elif action == 'sentence_boundary':
                tokens=project.get('transcript',{}).get('tokens',[])
                key=data.get('token_id');ids=[t['id'] for t in tokens]
                if key not in ids or key==ids[-1] or type(data.get('split')) is not bool:raise ValueError('请选择非末尾字词设置分句')
                i=ids.index(key)
                if not data['split'] and tokens[i].get('speaker','unknown')!=tokens[i+1].get('speaker','unknown'):raise ValueError('不同人物不能合并为一句，请先修正人物')
                breaks=set(project.get('manual_breaks',[]));joins=set(project.get('manual_joins',[]))
                if data['split']:breaks.add(key);joins.discard(key)
                else:
                    ends=preview_breaks(project)
                    if key not in ends:raise ValueError('请选择当前分句最后一个字，再取消该处分句')
                    j=ends.index(key)
                    if j+1>=len(ends):raise ValueError('最后一句不能再向后合并')
                    next_end=ends[j+1];start=ids.index(ends[j-1])+1 if j else 0
                    stop=ids.index(next_end)
                    if len({t.get('speaker','unknown') for t in tokens[start:stop+1]}-{'unknown'})>1:raise ValueError('不同人物不能合并为一句')
                    joins.update(ids[start:stop]);breaks.difference_update(ids[start:stop]);breaks.add(next_end)
                editorial.invalidate(project)
                project.update(manual_breaks=[v for v in ids if v in breaks],manual_joins=[v for v in ids if v in joins],subtitle_breaks=[],review_confirmed=False)
            elif action == 'speaker':
                label = data.get('speaker')
                if label not in ('A','B','unknown'):
                    raise ValueError('人物标签仅支持 A、B 或 unknown')
                tokens = project.get('transcript', {}).get('tokens', [])
                ids = data.get('token_ids', [])
                if not isinstance(ids, list) or not ids or any(not isinstance(i,str) for i in ids) or not set(ids) <= {t['id'] for t in tokens}:
                    raise ValueError('人物修正的字词范围无效')
                for t in tokens:
                    if t['id'] in ids:
                        t.update(speaker=label, speaker_manual=True)
                editorial.invalidate(project)
                project['review_confirmed']=False
                invalidate_semantic_suggestions(project)
                project['subtitle_breaks'] = []
            elif action in ("toggle", "adjust", "remove", 'review'):
                selected = next((c for c in project["candidates"] if c["id"] == data.get("id")), None)
                if selected is None:
                    raise ValueError("找不到删除建议")
                if action == "toggle":
                    if not isinstance(data.get("accepted"), bool):
                        raise ValueError("确认状态必须为布尔值")
                    selected["accepted"] = data["accepted"]
                elif action == 'review':
                    if data.get('category') not in ('auto','keep','no_dialogue','delete'):
                        raise ValueError('无效的分轨分类')
                    selected['review_action'] = data['category']
                    if data['category'] in ('keep','no_dialogue'):
                        selected['accepted'] = False
                elif action == "adjust":
                    selected["start"], selected["end"] = interval(data.get("start"), data.get("end"), project["media"]["duration"])
                    selected["timing_adjusted"] = True
                else:
                    project["candidates"] = [c for c in project["candidates"] if c["id"] != selected["id"]]
            elif action == "restore_all":
                for candidate in project["candidates"]:
                    candidate["accepted"] = False
            else:
                raise ValueError("未知修改操作")
            compact_plan(project)  # Reject deleting everything before persisting.
            project["edits_version"] += 1
            self.persist(project)
            if action == 'speaker':
                save_json(self.project_dir(project_id)/'transcript.json', project['transcript'])
        return self.view(project_id)

    def download(self, project_id, name):
        with self.lock:
            self.ensure_idle(project_id)
            project = self.load(project_id)
            directory = self.project_dir(project_id)
            if name == 'premiere.zip':
                manifest = directory/'premiere-manifest.json'
                if self.target != 'pr' or not manifest.is_file() or json.loads(manifest.read_text(encoding='utf-8'))['edits_version'] != project['edits_version']:
                    raise ValueError('PR 方案已变化或尚未生成，请重新生成工程交换包')
            if name == 'speaker_transcript.txt':
                (directory/name).write_text(speakers.annotated_text(project), encoding='utf-8-sig')
            elif name in ('review_plan.json', 'review_subtitles.srt'):
                plan = compile_review_plan(project)
                if name.endswith('json'):
                    save_json(directory/name, plan)
                else:
                    (directory/name).write_text(srt_text(review_subtitles(project, plan)), encoding='utf-8-sig')
            elif name in ("edit_plan.json", "subtitles.srt"):
                plan = compact_plan(project)
                if name.endswith("json"):
                    save_json(directory / name, plan)
                else:
                    (directory / name).write_text(srt_text(subtitle_cues(project, plan)), encoding="utf-8-sig")
            if name not in {"edit_plan.json", "subtitles.srt", "transcript.txt", "transcript.json", "silence.json", 'review_plan.json', 'review_subtitles.srt', 'speakers.json', 'speaker_transcript.txt', 'premiere.zip'}:
                raise ValueError("不支持的下载文件")
            path = directory / name
            if not path.exists():
                raise ValueError("文件尚未生成，请先转录")
            return path
