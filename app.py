"""Local-only application server. No public hosting; no API secrets in browser storage."""
import argparse
import json
import mimetypes
import os
import re
import secrets
import shutil
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from koubo.service import Service
from koubo.gap_close import close_jianying, close_premiere

ROOT = Path(__file__).resolve().parent


def create_server(service, port=8765):
    csrf = secrets.token_urlsafe(32)
    workspaces = {'jianying': service, 'pr': Service(service.directory/'premiere', 'pr', shared=service)}
    english_spaces = {'jianying': Service(service.directory/'english','jianying',shared=service,language='en'),
                      'pr': Service(service.directory/'english/premiere','pr',shared=service,language='en')}
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def guard(self, mutation=False):
            hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if self.headers.get("Host") not in hosts:
                raise ValueError("仅允许本机访问")
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://{h}" for h in hosts}:
                raise ValueError("拒绝跨站请求")
            if mutation and not secrets.compare_digest(self.headers.get("X-Koubo-Token", ""), csrf):
                raise ValueError("页面会话已更新，请刷新页面")

        def reply(self, payload, status=200):
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)

        def file(self, path, attachment=False):
            path = Path(path)
            if not path.is_file():
                raise ValueError("文件不存在或尚未生成")
            size, start, end = path.stat().st_size, 0, path.stat().st_size - 1
            request_range = self.headers.get("Range")
            partial = False
            if request_range:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", request_range)
                if not match or not any(match.groups()):
                    self.reply({"error": "无效 Range"}, 416)
                    return
                if match[1]:
                    start = int(match[1]); end = min(end, int(match[2])) if match[2] else end
                else:
                    start = max(0, size - int(match[2]))
                if start >= size or start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                partial = True
            self.send_response(206 if partial else 200)
            self.send_header("Content-Type", mimetypes.guess_type(str(path))[0] or "application/octet-stream")
            self.send_header("Content-Length", str(max(0, end - start + 1)))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if partial:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            if attachment:
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(path.name)}")
            if path.suffix in (".html", ".js", ".css"):
                self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            try:
                with path.open("rb") as source:
                    source.seek(start)
                    remaining = end - start + 1
                    while remaining > 0:
                        chunk = source.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def selected_service(self):
            params = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            targets = params.get('workspace', ['jianying'])
            languages = params.get('lang', ['zh'])
            if len(languages)!=1 or languages[0] not in ('zh','en'):
                raise ValueError('Unsupported language')
            if len(targets) != 1 or targets[0] not in workspaces:
                raise ValueError('无效或尚未开放的剪辑软件区块')
            return (english_spaces if languages[0]=='en' else workspaces)[targets[0]]

        def do_GET(self):
            try:
                self.guard()
                path = urllib.parse.urlsplit(self.path).path
                selected = service if path in ("/", "/app.js", "/i18n.js", "/style.css", "/logo.svg", "/favicon.ico") else self.selected_service()
                if path == "/api/state":
                    self.reply({**selected.status(), "csrf_token": csrf})
                elif path.startswith("/api/jobs/"):
                    with selected.lock:
                        job = selected.jobs.get(path.rsplit("/", 1)[-1])
                        if job is None:
                            raise ValueError("找不到任务")
                        snapshot = dict(job)
                        if job['action'] == 'summarize' and job['status'] in ('done','error'):
                            del selected.jobs[job['id']]  # One-shot delivery; no server-side summary history.
                        self.reply(snapshot)
                elif match := re.fullmatch(r"/api/projects/([a-f0-9]{16})", path):
                    self.reply(selected.view(match[1]))
                elif match := re.fullmatch(r"/gap-close/([a-f0-9]{16})/(result.zip|report.json)", path):
                    self.file(selected.directory/'gap-close'/match[1]/match[2], True)
                elif match := re.fullmatch(r"/download/([a-f0-9]{16})/([a-z_.]+)", path):
                    self.file(selected.download(match[1], match[2]), True)
                elif match := re.fullmatch(r"/media/([a-f0-9]{16})/(source|proxy.mp4|edited.mp4)", path):
                    project = selected.load(match[1])
                    source = Path(project["source_path"]) if match[2] == "source" else selected.project_dir(match[1]) / match[2]
                    if match[2] == "edited.mp4":
                        manifest = selected.project_dir(match[1]) / "edited-manifest.json"
                        if not manifest.exists() or json.loads(manifest.read_text())["edits_version"] != project["edits_version"]:
                            raise ValueError("剪辑方案已变化，请重新渲染 MP4")
                    self.file(source)
                elif path in ("/", "/app.js", "/i18n.js", "/style.css", "/logo.svg", "/favicon.ico"):
                    self.file(ROOT / "static" / ("index.html" if path == "/" else path[1:]))
                else:
                    self.reply({"error": "找不到页面"}, 404)
            except (ValueError, OSError) as error:
                self.reply({"error": str(error)[:2000]}, 400)

        def do_POST(self):
            try:
                self.guard(True)
                selected = self.selected_service()
                path = urllib.parse.urlsplit(self.path).path
                size = int(self.headers.get("Content-Length", "0"))
                if path == "/api/upload":
                    if not 0 < size <= 20 * 1024**3:
                        raise ValueError("上传文件需为 1 字节至 20 GB；大文件建议使用原片路径")
                    name = Path(urllib.parse.unquote(self.headers.get("X-Filename", "video.mp4"))).name
                    extension = Path(name).suffix.lower()
                    if extension not in {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}:
                        raise ValueError("不支持的视频格式")
                    uploads = selected.directory / "uploads"
                    uploads.mkdir(exist_ok=True)
                    target = uploads / (secrets.token_hex(8) + extension)
                    remaining = size
                    with target.open("wb") as output:
                        while remaining:
                            chunk = self.rfile.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise ValueError("视频上传被中断")
                            output.write(chunk)
                            remaining -= len(chunk)
                    project = selected.import_video(target)
                    project["media"]["name"] = name
                    with selected.lock:
                        stored = selected.load(project["id"])
                        stored["media"]["name"] = name
                        selected.persist(stored)
                    self.reply(selected.view(project["id"]))
                    return
                if not 0 <= size <= 2 * 1024 * 1024:
                    raise ValueError("请求内容过大")
                data = json.loads(self.rfile.read(size) or b"{}")
                if not isinstance(data, dict):
                    raise ValueError("请求必须是 JSON 对象")
                if path == "/api/settings":
                    self.reply(selected.configure(data))
                elif path == '/api/gap-close':
                    if not isinstance(data.get('path'), str) or not data['path'].strip():
                        raise ValueError('请填写已保存草稿或 XML 的本机路径')
                    token = secrets.token_hex(8)
                    output = selected.directory/'gap-close'/token
                    if selected.target == 'pr':
                        result = close_premiere(data['path'].strip().strip('"'), output)
                        result['download'] = f'/gap-close/{token}/result.zip?workspace=pr&lang={selected.language}'
                    else:
                        result = close_jianying(data['path'].strip().strip('"'))
                        output.mkdir(parents=True, exist_ok=False)
                    (output/'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                    result['report'] = f'/gap-close/{token}/report.json?workspace={selected.target}&lang={selected.language}'
                    self.reply(result)
                elif path == "/api/import":
                    self.reply(selected.import_video(data.get("path", "")))
                elif path == "/api/jobs":
                    action = data.get("action")
                    if action not in {"download_model", "transcribe", "rules", "analyze", "proxy", "draft", "render", 'download_speakers', 'diarize', 'prepare', 'premiere', 'summarize'}:
                        raise ValueError("未知任务")
                    self.reply(selected.start_job(action, data.get("project_id"), data.get("options", {})))
                elif match := re.fullmatch(r"/api/projects/([a-f0-9]{16})/(archive|restore)", path):
                    self.reply(selected.archive_project(match[1],restore=match[2]=='restore',archive_id=data.get('archive_id')))
                elif match := re.fullmatch(r"/api/projects/([a-f0-9]{16})/edits", path):
                    self.reply(selected.update_candidates(match[1], data))
                else:
                    self.reply({"error": "未知接口"}, 404)
            except (ValueError, OSError, TypeError, KeyError) as error:
                self.close_connection = True
                self.reply({"error": str(error)[:2000]}, 400)
            except Exception:
                self.close_connection = True
                self.reply({"error": "操作失败，请检查文件格式或重新启动。原视频不会被修改。"}, 500)
    server=ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.workspaces=workspaces
    server.english_workspaces=english_spaces
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = create_server(Service(args.data_dir), args.port)
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Koubo Cut Beta: {url}\nKeep this window open. Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        threading.Timer(1, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
