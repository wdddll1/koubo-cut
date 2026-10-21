"""Windows executable entry point; resources are bundled, user data stays outside the EXE."""
import argparse
import hashlib
import json
import os
import sys
import threading
import traceback
import urllib.request
from pathlib import Path

RESOURCE_ROOT=Path(__file__).resolve().parent


def default_data():
    if getattr(sys,'frozen',False):
        if (Path(sys.executable).parent/'portable.json').is_file():
            return (Path(sys.executable).parent/'data').resolve()
        legacy=Path(sys.executable).parent/'koubo-cut-beta'/'data'
        if legacy.is_dir():return legacy.resolve()
    return Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'KouboCut'/'data'


def existing_server(directory):
    ports=list(range(8765,8776))
    runtime=directory/'desktop-runtime.json'
    if runtime.is_file():
        try:ports.insert(0,int(json.loads(runtime.read_text(encoding='utf-8'))['port']))
        except (ValueError,KeyError,OSError):pass
    for port in ports:
        try:
            request=urllib.request.Request(f'http://127.0.0.1:{port}/api/state')
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=.25) as response:
                state=json.load(response)
            if Path(state.get('data_directory','')).resolve()==directory.resolve() and 'KouboCut' not in state.get('error','') and state.get('version'):
                return f'http://127.0.0.1:{port}/'
        except (OSError,ValueError):pass
    return None


def create_runtime(directory,port=None):
    from app import create_server
    from koubo.service import Service
    from koubo.portable import relocate
    from koubo.runtime_tools import configure
    relocate(directory)
    configure(directory)
    service=Service(directory)
    model_candidates=[directory/'models']
    if getattr(sys,'frozen',False):model_candidates.append(Path(sys.executable).parent/'data'/'models')
    model_candidates.append(RESOURCE_ROOT/'models')
    for candidate in model_candidates:
        if candidate.is_dir():
            service.model_root=candidate;break
    if port is not None:return service,create_server(service,port)
    # Let Windows allocate an unused port; an older local server may still run.
    return service,create_server(service,0)


def self_test(args,directory):
    from koubo import media
    from koubo.service import Service
    import tkinter as tk
    service,server=create_runtime(directory,0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    result={'packaged':bool(getattr(sys,'frozen',False)),'executable':sys.executable}
    try:
        ui=tk.Tk();ui.withdraw();ui.update_idletasks();ui.destroy();result['window_runtime']=True
        url=f'http://127.0.0.1:{server.server_port}'
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url+'/api/state',timeout=5) as response:state=json.load(response)
        with opener.open(url+'/',timeout=5) as response:page=response.read().decode()
        result.update(http_ready=True,model_ready=state['model_ready'],speaker_model_ready=state['speaker_model_ready'],manual_cut_option='id="manual-cut"' in page)
        if args.test_media:
            p=service.import_video(args.test_media)
            service.execute('prepare',p['id'],{'speakers':2},dict(service.settings),lambda *a:None)
            p=service.load(p['id']);p.setdefault('workflow',{}).update(manual_cut=True,draft_name='EXE打包验证',direct_delete=False)
            service.persist(p)
            jy=service.execute('draft',p['id'],{'root':str(directory/'test-drafts'),'mode':'review','subtitles':True},dict(service.settings),lambda *a:None)
            pr=Service(directory/'premiere','pr',shared=service)
            pr.project_dir(p['id']).mkdir(parents=True,exist_ok=True);pr.persist(p)
            exchange=pr.execute('premiere',p['id'],{'mode':'review','subtitles':True},dict(pr.settings),lambda *a:None)
            result.update(asr_words=len(p['transcript']['tokens']),speakers=p['diarization']['speaker_count'],jianying_segments=jy['segments'],pr_segments=exchange['segments'],pr_subtitle_clips=exchange.get('subtitle_clips',0),paid_api_called=False,original_sha256=media.source_hash(args.test_media))
        result['success']=True
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
    return result


def show_window(directory, language=None):
    print('Launcher: loading window',flush=True)
    import tkinter as tk
    from tkinter import messagebox,ttk
    import webbrowser
    root=tk.Tk();root.title('口播快剪 · Windows 测试版');root.geometry('590x330');root.resizable(False,False)
    root.iconbitmap(str(RESOURCE_ROOT/'assets/logo.ico'))
    root.configure(bg='#f4f6f0')
    print('Launcher: configuring controls',flush=True)
    ttk.Style(root).configure('TButton',padding=9)
    status=tk.StringVar(value='正在启动本地工作台…')
    tk.Label(root,text='口播快剪',font=('Microsoft YaHei UI',25,'bold'),bg='#f4f6f0',fg='#25352c').pack(anchor='w',padx=30,pady=(26,4))
    tk.Label(root,text='本地识别 · 人工复核 · 剪映 / PR 工程制作',font=('Microsoft YaHei UI',11),bg='#f4f6f0',fg='#70806a').pack(anchor='w',padx=32)
    tk.Label(root,textvariable=status,font=('Microsoft YaHei UI',11),bg='#f4f6f0',wraplength=525,justify='left').pack(anchor='w',padx=32,pady=20)
    tk.Label(root,text='项目数据：'+str(directory),font=('Microsoft YaHei UI',9),bg='#f4f6f0',wraplength=525,justify='left',fg='#7c8576').pack(anchor='w',padx=32)
    row=ttk.Frame(root);row.pack(anchor='w',padx=30,pady=20)
    state={'server':None,'service':None,'url':None,'lock':None}
    def open_page():
        if state['url']:webbrowser.open(state['url']+(f'?lang={language}' if language else ''))
    button=ttk.Button(row,text='打开工具页面',command=open_page,state='disabled');button.pack(side='left',padx=(0,10))
    ttk.Button(row,text='打开数据目录',command=lambda:os.startfile(str(directory))).pack(side='left',padx=(0,10))
    def close():
        service=state['service']
        if service:
            with service.lock:
                jobs=[j for svc in [*state['server'].workspaces.values(),*state['server'].english_workspaces.values()] for j in svc.jobs.values() if j['status']=='running']
            if jobs and not messagebox.askyesno('任务正在运行','退出会中断正在运行的任务，仍要退出吗？',parent=root):return
        if state['server']:state['server'].shutdown();state['server'].server_close()
        if state['lock']:state['lock'].close()
        root.destroy()
    ttk.Button(row,text='退出软件',command=close).pack(side='left')
    root.protocol('WM_DELETE_WINDOW',close)
    print('Launcher: controls ready',flush=True)
    def initialize():
        try:
            print('Launcher: checking local server',flush=True)
            attached=existing_server(directory)
            if attached:
                state['url']=attached;status.set('已连接当前运行的工作台；关闭此窗口不会停止原服务。')
            else:
                import msvcrt
                lock=(directory/'desktop.lock').open('a+b');lock.seek(0)
                if lock.read(1)==b'':lock.write(b'0');lock.flush()
                lock.seek(0)
                try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
                except OSError:
                    lock.close();messagebox.showinfo('口播快剪','软件已在运行，请使用已有窗口或稍后再次打开。',parent=root);root.destroy();return
                state['lock']=lock
                service,server=create_runtime(directory)
                state.update(service=service,server=server,url=f'http://127.0.0.1:{server.server_port}/')
                (directory/'desktop-runtime.json').write_text(json.dumps({'port':server.server_port,'pid':os.getpid()}),encoding='utf-8')
                threading.Thread(target=server.serve_forever,daemon=True).start()
                status.set('软件已启动。关闭此窗口会停止本软件的本地服务。')
            button.configure(state='normal');open_page()
        except Exception:
            traceback.print_exc();messagebox.showerror('启动失败','请检查数据目录中的 desktop.log。',parent=root);root.destroy()
    root.after(100,initialize);root.mainloop()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,default=None)
    parser.add_argument('--self-test-report',type=Path)
    parser.add_argument('--test-media',type=str)
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--ready-file',type=Path)
    parser.add_argument('--language',choices=('zh','en'),help='Open the page in Chinese or English; also selects its speech model')
    args=parser.parse_args()
    directory=(args.data_dir or default_data()).resolve();directory.mkdir(parents=True,exist_ok=True)
    if (directory/'portable.json').is_file():
        cache=directory/'cache';temporary=cache/'temp';temporary.mkdir(parents=True,exist_ok=True)
        for key in ('TEMP','TMP','TMPDIR'):os.environ[key]=str(temporary)
        os.environ['XDG_CACHE_HOME']=str(cache)
        import tempfile
        tempfile.tempdir=str(temporary)
    log=(directory/'desktop.log').open('a',encoding='utf-8',buffering=1)
    sys.stdout=sys.stderr=log
    if args.self_test_report:
        try:result=self_test(args,directory)
        except Exception:
            traceback.print_exc();result={'success':False,'error':traceback.format_exc()}
        args.self_test_report.parent.mkdir(parents=True,exist_ok=True)
        args.self_test_report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return 0 if result['success'] else 1
    if args.headless:
        service,server=create_runtime(directory,args.port)
        if args.ready_file:args.ready_file.write_text(json.dumps({'port':server.server_port,'pid':os.getpid(),'packaged':bool(getattr(sys,'frozen',False))}),encoding='utf-8')
        try:server.serve_forever()
        finally:server.server_close()
    else:
        # Load media/COM dependencies before entering Tk's event callback.
        # Importing the Windows automation dependency from a Tk callback can
        # recursively pump messages and leave an uninitialized launcher window.
        print('Launcher: loading media dependencies',flush=True)
        from app import create_server
        from koubo.service import Service
        show_window(directory,args.language)
    return 0


if __name__=='__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
