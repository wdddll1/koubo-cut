'use strict';
const $ = id => document.getElementById(id);
let appState, project = null, busy = false, editing = false, selection = [], audition = null, activeToken = null;
const video = $('video');
let workspace=['pr','ae'].includes(new URLSearchParams(location.search).get('workspace'))?new URLSearchParams(location.search).get('workspace'):'jianying';
let aiTask='analyze', summarySnapshot='';
const spaceViews={};
function workspaceURL(path){const u=new URL(path,location.origin);u.searchParams.set('lang',KouboI18n.language);if(workspace==='pr')u.searchParams.set('workspace','pr');return u.pathname+u.search;}

const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const formatTime = ms => {const sec = Math.max(0, ms / 1000); return `${Math.floor(sec / 60).toString().padStart(2,'0')}:${(sec % 60).toFixed(1).padStart(4,'0')}`;};
const seconds = value => (value / 1000).toFixed(3);
let messageTimer;
function message(text, error=false) { clearTimeout(messageTimer); $('message').textContent=text; $('message').classList.toggle('error',error); $('message').hidden=false; messageTimer=setTimeout(()=> $('message').hidden=true,error?18000:7000); }
async function api(path, data) {
  const response = await fetch(workspaceURL(path), data === undefined ? {cache:'no-store'} : {method:'POST',headers:{'Content-Type':'application/json','X-Koubo-Token':appState.csrf_token},body:JSON.stringify(data)});
  const result = await response.json(); if (!response.ok) throw new Error(result.error || '请求失败'); return result;
}
function protect(action) { return async event => { try { await action(event); } catch(error) { message(error.message,true); } }; }
function setBusy(value) {
  busy=value;
  const controls=['gap-close','gap-path','transcribe','rules','analyze','manual-add','restore-all','draft','render','model-download','create-proxy','import-path','file-input','new-project','delete-selection','diarize','speaker-model','speaker-count','speaker-selection','assign-speaker','prepare','select-all','deselect-all','manual-cut','compression-enabled','retention','direct-delete','draft-name','draft-mode','include-subtitles','summary-load','summary-analyze','summary-source','split-sentence','join-sentence','review-confirmed'];
  for (const id of controls) $(id).disabled=value;
  document.querySelectorAll('.suggestion button,.suggestion input,.suggestion select,.project-item,.project-remove,[data-restore]').forEach(node=>node.disabled=value);
  document.querySelectorAll('[data-space]').forEach(n=>n.disabled=value);
  $('job-panel').hidden=!value;
  if(project)renderRetention();
  $('summary-load').disabled=value||!project||workspace==='ae';
  $('new-project').disabled=value||workspace==='ae';
  $('review-confirmed').disabled=value||project?.diarization?.status!=='done';
}
async function refreshState() { appState=await api('/api/state'); renderSidebar(); }
function renderSidebar() {
  $('project-count').textContent=appState.projects.length;
  $('projects').innerHTML=appState.projects.map(p=>`<div class="project-row"><button class="project-item ${project?.id===p.id?'selected':''}" data-project="${p.id}"><strong>${escapeHTML(p.name)}</strong><small>${formatTime(p.duration)} · ${p.transcribed?'已转录':'待转录'}</small></button><button class="project-remove" data-remove="${p.id}" title="移除最近素材，原视频保留" aria-label="移除 ${escapeHTML(p.name)}">×</button></div>`).join('');
  $('projects').querySelectorAll('[data-project]').forEach(node=>node.addEventListener('click',protect(async()=>{if(busy)return; await openProject(node.dataset.project);} )));
  $('projects').querySelectorAll('[data-remove]').forEach(n=>n.addEventListener('click',protect(async()=>{
    if(busy||editing)return;const id=n.dataset.remove;
    await api(`/api/projects/${id}/archive`,{});
    if(project?.id===id){video.pause();video.removeAttribute('src');project=null;selection=[];audition=null;$('editor').hidden=true;$('import-panel').hidden=workspace==='ae';$('project-name').textContent=KouboI18n.translate('新建粗剪');}
    if(spaceViews[workspace]?.id===id)delete spaceViews[workspace].id;
    await refreshState();message('已移入工具回收站，原视频保留，可恢复');
  })));
  const trash=appState.archived_projects||[];
  $('trash-count').textContent=`回收站（${trash.length}）`;
  $('trash-projects').innerHTML=trash.map(p=>`<div class="trash-row"><span>${escapeHTML(p.name)}</span><button class="text-button" data-restore="${p.id}" data-archive="${p.archive_id}">恢复</button></div>`).join('');
  $('trash-projects').querySelectorAll('[data-restore]').forEach(n=>n.addEventListener('click',protect(async()=>{if(busy||editing)return;await api(`/api/projects/${n.dataset.restore}/restore`,{archive_id:n.dataset.archive});await refreshState();message('素材项目已恢复');})));
  $('trash-panel').hidden=workspace==='ae';
  $('model-status').textContent=appState.model_ready?'● 中文识别模型已就绪':'○ 首次使用需下载中文模型';
  $('model-download').hidden=appState.model_ready;
  $('speaker-model').hidden=appState.speaker_model_ready;
  $('summary-load').disabled=busy||!project||workspace==='ae';
}
async function openProject(id) {
  video.pause(); audition=null; selection=[]; activeToken=null;
  project=await api(`/api/projects/${id}`);
  loadWorkflow();
  const source=workspaceURL(`/media/${project.id}/source`);
  video.src=source; video.load(); $('codec-help').hidden=true;
  $('export-result').hidden=true; renderProject(); renderSidebar();
}
function renderProject() {
  if(!project||workspace==='ae')return;
  $('import-panel').hidden=true; $('editor').hidden=false; $('project-name').textContent=project.media.name;
  $('original-duration').textContent=formatTime(project.media.duration);
  $('edited-duration').textContent=formatTime(project.plan.output_duration);
  $('saved-duration').textContent=formatTime(project.media.duration-project.plan.output_duration);
  renderRetention();
  const tokens=project.transcript?.tokens||[];
  $('token-count').textContent=tokens.length?`${tokens.length} 个字词 · ${project.candidates.filter(c=>c.accepted).length} 项已确认`:'尚未转录';
  $('transcribe').textContent=tokens.length?'复用转录缓存':'开始中文转录';
  $('transcript-empty').hidden=Boolean(tokens.length); $('transcript').hidden=!tokens.length;
  const polished=project.editorial;
  $('review-confirmed').checked=project.review_confirmed===true;
  $('review-confirmed').disabled=busy||project.diarization?.status!=='done';
  $('rules').hidden=project.editing_policy==='sentences';
  $('transcript-badge').textContent=polished?`整句 ${polished.sentences.length} 段 · 校正 ${Object.keys(polished.corrections).length} 处`:tokens.length?'本地预分段 · 待人工复核':'待识别';
  $('download-transcript').hidden=!tokens.length; $('download-transcript').href=`/download/${project.id}/speaker_transcript.txt`;
  $('download-plan').href=`/download/${project.id}/edit_plan.json`; $('download-srt').href=`/download/${project.id}/subtitles.srt`;
  $('download-review').href=`/download/${project.id}/review_plan.json`; $('download-review-srt').href=`/download/${project.id}/review_subtitles.srt`;
  $('speaker-status').textContent=project.diarization?.status==='done'?`${project.diarization.speaker_count} 组声纹 · 待复核`:'尚未标记';
  $('speaker-note').textContent=project.diarization?.note||'先转录，再运行本地声纹分组；A/B 是匿名人物标签，可选中文字修正。';
  const warnings=[...(project.warnings||[]),...(project.transcript?.warnings||[]),...(project.plan.warnings||[])];
  if(tokens.length) warnings.push(project.transcript.timing_note || '字词切点需要试听确认。');
  $('project-warnings').hidden=!warnings.length; $('project-warnings').textContent=[...new Set(warnings)].join('\n');
  const deletes=project.plan.resolved_delete_ranges;
  let html='',line=[],lineStart=0;
  const selectedMin=selection.length?Math.min(...selection):-1, selectedMax=selection.length?Math.max(...selection):-1;
  let lineSpeaker='unknown';
  function flush() {if(line.length){html+=`<div class="transcript-line"><span class="time-label">${formatTime(lineStart)}</span><span class="speaker-tag speaker-${escapeHTML(lineSpeaker)}">${lineSpeaker==='unknown'?'待定':escapeHTML(lineSpeaker)}</span>${line.join('')}</div>`;line=[];}}
  tokens.forEach((token,index)=>{
    if(index && (project.editing_policy==='sentences' ? (project.preview_breaks||[]).includes(tokens[index-1].id) || token.speaker!==tokens[index-1].speaker : line.length>=24 || token.start-tokens[index-1].end>500 || token.speaker!==tokens[index-1].speaker))flush();
    if(!line.length){lineStart=token.start;lineSpeaker=token.speaker||'unknown';}
    const deleted=deletes.some(([a,b])=>token.start<b && token.end>a);
    const selected=index>=selectedMin && index<=selectedMax;
    line.push(`<button type="button" class="token ${deleted?'deleted':''} ${selected?'selected':''} ${token.aligned===false?'unaligned':''} ${token.corrected_text?'corrected':''}" data-index="${index}" title="${escapeHTML(token.id)} · ${seconds(token.start)}–${seconds(token.end)} 秒${token.corrected_text?' · 原识别：'+escapeHTML(token.text):''}">${escapeHTML(token.corrected_text??token.text)}</button>`);
  });flush(); $('transcript').innerHTML=html;
  $('transcript').querySelectorAll('.token').forEach(node=>node.addEventListener('click',event=>{
    const index=Number(node.dataset.index);
    if(event.shiftKey && selection.length){selection=[selection[0],index];} else {selection=[index]; audition=null;video.currentTime=tokens[index].start/1000;}
    updateSelection();
  }));
  updateSelection(); renderSuggestions(); renderReviewTracks();
  for(const id of ['download-transcript','download-plan','download-srt','download-review','download-review-srt'])$(id).href=workspaceURL($(id).getAttribute('href'));
  renderWorkspaceLabels();
  const stage=tokens.length?(project.candidates.some(c=>c.accepted)?3:2):1;
  document.querySelectorAll('.steps li').forEach((node,index)=>node.classList.toggle('current',index+1<=stage));
}
function updateSelection(){
  const min=selection.length?Math.min(...selection):-1,max=selection.length?Math.max(...selection):-1;
  $('transcript').querySelectorAll('.token').forEach(node=>node.classList.toggle('selected',Number(node.dataset.index)>=min && Number(node.dataset.index)<=max && min>=0));
  $('selection-bar').hidden=!selection.length;
  if(selection.length){const tokens=project.transcript.tokens; $('selection-label').textContent=`已选 ${max-min+1} 个字词 · ${formatTime(tokens[min].start)}—${formatTime(tokens[max].end)}`;}
}
function renderSuggestions(){
  const candidates=[...project.candidates].sort((a,b)=>a.start-b.start);
  $('suggestion-count').textContent=candidates.length;
  $('suggestions-empty').hidden=Boolean(candidates.length);
  $('suggestions-empty').textContent=project.transcript?.tokens?.length?'暂无删除建议。可进行 AI 分析，或选择文字手动剪辑。':'先识别文稿与人物，再由 AI 校正并按完整句子规划。';
  const types={filler:'语气助词 → 无内容',silence:'长停顿',repeat:'相邻重复',ai:'AI 建议',manual:'手动删除'};
  $('suggestions').innerHTML=candidates.map(c=>`<article class="suggestion ${c.accepted?'accepted':''}" data-id="${c.id}">
    <input type="checkbox" data-action="toggle" aria-label="确认删除 ${escapeHTML(c.text)}" ${c.accepted?'checked':''}>
    <div class="suggestion-time">${formatTime(c.start)}<span>至 ${formatTime(c.end)} / ${((c.end-c.start)/1000).toFixed(2)}s</span></div>
    <div class="suggestion-text"><span class="type">${types[c.kind]||'建议'}</span>${escapeHTML(c.text)}${c.protected?'<span class="protect">涉及关键信息，请重点复核</span>':''}<small>${escapeHTML(c.reason)}</small></div>
    <div class="suggestion-buttons"><select data-action="review" aria-label="分轨分类">${[['auto','自动分轨'],['keep','保留（保护转场）'],['no_dialogue','无内容／语气助词'],['delete','建议删除轨道']].map(([v,l])=>`<option value="${v}" ${(c.review_action||'auto')===v?'selected':''}>${l}</option>`).join('')}</select><button class="text-button" data-action="original">原片试听</button><button class="text-button" data-action="cut">跳过试听</button><button class="text-button" data-action="adjust">微调</button>${c.kind==='manual'?'<button class="text-button" data-action="remove">移除</button>':''}</div>
    <div class="adjust-row" hidden><span>秒</span><input class="adjust-start" type="number" step="0.01" min="0" value="${seconds(c.start)}"><span>→</span><input class="adjust-end" type="number" step="0.01" min="0" value="${seconds(c.end)}"><button class="text-button" data-action="save-adjust">保存切点</button></div>
  </article>`).join('');
  $('suggestions').querySelectorAll('.suggestion').forEach(row=>{
    const candidate=candidates.find(c=>c.id===row.dataset.id);
    row.querySelectorAll('[data-action]').forEach(node=>node.addEventListener(node.type==='checkbox'||node.tagName==='SELECT'?'change':'click',protect(async()=>{
      const action=node.dataset.action;
      if(action==='original'||action==='cut'){auditionCandidate(candidate,action==='cut');return;}
      if(action==='adjust'){row.querySelector('.adjust-row').hidden=!row.querySelector('.adjust-row').hidden;return;}
      if(action==='toggle')await mutate({action:'toggle',id:candidate.id,accepted:node.checked});
      if(action==='review')await mutate({action:'review',id:candidate.id,category:node.value});
      if(action==='remove')await mutate({action:'remove',id:candidate.id});
      if(action==='save-adjust')await mutate({action:'adjust',id:candidate.id,start:Math.round(Number(row.querySelector('.adjust-start').value)*1000),end:Math.round(Number(row.querySelector('.adjust-end').value)*1000)});
    })));
  });
  if(busy)document.querySelectorAll('.suggestion button,.suggestion input,.suggestion select').forEach(node=>node.disabled=true);
}
function renderReviewTracks(){
  const plan=project.review_plan,duration=project.media.duration;
  if(!plan)return;
  $('review-duration').textContent=`原时长 ${formatTime(duration)} · ${plan.segments.length} 段`;
  const rows=workspace==='pr'?[['keep','V4 · 保留'],['no_dialogue','V3 · 无内容'],['delete','V2 · 建议删除']]:[['keep','画中画0 · 保留'],['no_dialogue','画中画1 · 无内容'],['delete','画中画2 · 建议删除']];
  $('review-tracks').innerHTML=rows.map(([kind,label])=>`<div class="review-row"><span>${label}</span><div class="review-lane">${plan.segments.filter(c=>c.category===kind).map(c=>`<button class="review-clip ${kind}" data-start="${c.start}" title="${label} ${formatTime(c.start)}—${formatTime(c.end)}" aria-label="${label} ${seconds(c.start)} 至 ${seconds(c.end)} 秒"></button>`).join('')}</div></div>`).join('')+'<div class="review-row"><span>主轨道 · 黑色</span><div class="review-lane black-base"></div></div>';
  const clips=plan.segments;
  $('review-tracks').querySelectorAll('[data-start]').forEach(n=>{
    const clip=clips.find(c=>c.start===Number(n.dataset.start));
    // Set geometry through CSSOM; the local CSP rejects inline style attributes.
    n.style.left=`${100*clip.start/duration}%`;n.style.width=`${100*(clip.end-clip.start)/duration}%`;
    n.addEventListener('click',()=>{audition=null;$('skip-deletions').checked=false;video.currentTime=Number(n.dataset.start)/1000;$('playback-label').textContent='原时间轴';});
  });
}
async function mutate(data){
  if(busy||editing)throw new Error('请等待当前操作完成');
  editing=true;
  try{const updated=await api(`/api/projects/${project.id}/edits`,{...data,edits_version:project.edits_version});project=updated;audition=null;selection=[];renderProject();$('export-result').hidden=true;}
  catch(error){project=await api(`/api/projects/${project.id}`);renderProject();throw error;}
  finally{editing=false;}
}
async function startJob(action,options={}){
  if(busy||editing)throw new Error('请等待当前任务完成');
  if(!['download_model','download_speakers','summarize'].includes(action)&&!project)throw new Error('请先导入视频');
  setBusy(true);video.pause();audition=null;
  try{
    const started=await api('/api/jobs',{action,project_id:project?.id,options});
    let result;
    for(;;){const job=await api(`/api/jobs/${started.job_id}`);$('job-message').textContent=job.message;$('job-percent').textContent=`${job.progress}%`;$('job-progress').style.width=`${job.progress}%`;
      if(job.status==='error')throw new Error(job.message);
      if(job.status==='done'){result=job.result;break;}
      await new Promise(resolve=>setTimeout(resolve,800));
    }
    if(project){project=await api(`/api/projects/${project.id}`);renderProject();}
    await refreshState();
    if(action==='summarize'){$('summary-result').value=result.text;message('标题、标题、主题与精简主体已反馈，可修改、复制并对照原文');}
    else if(action==='premiere'){$('export-result').innerHTML=`<strong>已生成 PR 工程交换包 · ${result.segments} 个片段</strong><p>${escapeHTML(result.path)}</p><p>${escapeHTML(result.note)}</p><a class="button small dark" href="${escapeHTML(workspaceURL(result.url))}" download>下载 PR 工程交换包 ZIP ↓</a>`;$('export-result').hidden=false;}
    else if(action==='proxy'){video.src=workspaceURL(result.url)+`&t=${Date.now()}`;video.load();$('codec-help').hidden=true;}
    else if(action==='draft'){ $('export-result').innerHTML=`<strong>已生成独立剪映草稿 · ${result.segments} 个片段</strong><p>${escapeHTML(result.path)}</p><p>${escapeHTML(result.note)}</p><p>请使用你指定的剪映 5.9 打开草稿。文件生成成功不等于已完成剪映端兼容验收。</p>`;$('export-result').hidden=false;}
    else if(action==='render'){ $('export-result').innerHTML=`<strong>剪辑 MP4 已生成</strong><p>${escapeHTML(result.path)}</p><a href="${workspaceURL(result.url)}" download="口播粗剪.mp4">下载 MP4 ↓</a>`;$('export-result').hidden=false;}
    else message(action==='prepare'?`文稿与人物识别完成：${result.speaker_count} 组声纹，请复核`:['analyze','prepare_editorial'].includes(action)?`整句 ${result.sentences} 段，校正 ${result.corrections} 处，语气助词 ${result.fillers} 段；请试听复核`:action==='diarize'?`识别到 ${result.speaker_count} 组声纹，请复核 A/B 标签`:action==='download_speakers'?'说话人模型已就绪':action==='download_model'?'中文识别模型已准备完成':result.cached?'已复用转录缓存':'处理完成，请试听确认');
    return result;
  }catch(error){if(project){try{project=await api(`/api/projects/${project.id}`);renderProject();}catch{}}throw error;}finally{setBusy(false);}
}
function playbackRanges(){
  if(audition)return audition.ranges;
  if(!project)return[];
  return $('skip-deletions').checked?project.plan.resolved_keep_ranges.map(k=>[k.start,k.end]):[[0,project.media.duration]];
}
function enforcePlayback(){
  if(video.paused||!project)return;
  const ranges=playbackRanges(),time=video.currentTime*1000;
  const current=ranges.find(([start,end])=>time>=start-10&&time<end-8);
  if(!current){const next=ranges.find(([start])=>start>time);if(next){video.currentTime=next[0]/1000;}else{video.pause();if(audition)message('切点试听结束');}}
  const tokens=project.transcript?.tokens||[];const token=tokens.findIndex(t=>time>=t.start&&time<t.end);
  if(token!==activeToken){document.querySelector('.token.playing')?.classList.remove('playing');document.querySelector(`.token[data-index="${token}"]`)?.classList.add('playing');activeToken=token;}
}
function auditionCandidate(candidate,cut){
  const left=Math.max(0,candidate.start-1200),right=Math.min(project.media.duration,candidate.end+1200);
  const ranges=cut?[[left,candidate.start],[candidate.end,right]].filter(([a,b])=>b>a):[[left,right]];
  if(!ranges.length){message('这个区间没有可试听的相邻内容',true);return;}
  audition={ranges};$('playback-label').textContent=cut?'跳过候选试听':'候选原片试听';video.currentTime=ranges[0][0]/1000;video.play().catch(error=>message('请点击视频播放按钮试听',true));
}
video.addEventListener('timeupdate',enforcePlayback);video.addEventListener('play',enforcePlayback);
video.addEventListener('error',()=>{$('codec-help').hidden=false;});
$('skip-deletions').addEventListener('change',()=>{audition=null;$('playback-label').textContent=$('skip-deletions').checked?'剪后试听':'原片';});
$('replay').addEventListener('click',protect(async()=>{audition=null;const ranges=playbackRanges();video.currentTime=(ranges[0]?.[0]||0)/1000;$('playback-label').textContent=$('skip-deletions').checked?'剪后试听':'原片';await video.play();}));
$('new-project').addEventListener('click',()=>{if(busy||workspace==='ae')return;video.pause();project=null;selection=[];audition=null;$('editor').hidden=true;$('import-panel').hidden=false;$('project-name').textContent=KouboI18n.translate('新建粗剪');renderSidebar();});
$('import-path').addEventListener('click',protect(async()=>{if(busy)return;setBusy(true);$('job-message').textContent='读取视频并建立素材指纹';try{const imported=await api('/api/import',{path:$('source-path').value});await openProject(imported.id);await refreshState();message('原片已导入，下一步开始中文转录');}finally{setBusy(false);}}));
async function uploadFile(file){
  if(!file||busy)return;setBusy(true);$('job-message').textContent='复制视频到本机数据目录，建立素材档案';
  try{const response=await fetch(workspaceURL('/api/upload'),{method:'POST',headers:{'X-Koubo-Token':appState.csrf_token,'X-Filename':encodeURIComponent(file.name),'Content-Type':'application/octet-stream'},body:file});const result=await response.json();if(!response.ok)throw new Error(result.error);await openProject(result.id);await refreshState();message('视频已导入');}finally{setBusy(false);$('file-input').value='';}
}
$('dropzone').addEventListener('click',()=>{if(!busy)$('file-input').click();});
$('dropzone').addEventListener('keydown',event=>{if(event.key==='Enter'&&!busy)$('file-input').click();});
$('file-input').addEventListener('change',protect(event=>uploadFile(event.target.files[0])));
$('dropzone').addEventListener('dragover',event=>{event.preventDefault();$('dropzone').classList.add('dragging');});
$('dropzone').addEventListener('dragleave',()=> $('dropzone').classList.remove('dragging'));
$('dropzone').addEventListener('drop',protect(async event=>{event.preventDefault();$('dropzone').classList.remove('dragging');await uploadFile(event.dataTransfer.files[0]);}));
$('model-download').addEventListener('click',protect(()=>startJob('download_model')));
$('speaker-model').addEventListener('click',protect(()=>startJob('download_speakers')));
$('diarize').addEventListener('click',protect(async()=>{if(!project?.transcript?.tokens?.length)throw new Error('请先完成中文转录');if(!appState.speaker_model_ready)await startJob('download_speakers');await startJob('diarize',{speakers:Number($('speaker-count').value)});}));
$('speaker-selection').addEventListener('click',protect(async()=>{if(!selection.length)return;const lo=Math.min(...selection),hi=Math.max(...selection);await mutate({action:'speaker',speaker:$('assign-speaker').value,token_ids:project.transcript.tokens.slice(lo,hi+1).map(t=>t.id)});message('人物已修正，请复核分句并重新勾选复核确认，再提交 AI');}));
$('transcribe').addEventListener('click',protect(async()=>{if(!appState.model_ready){message('请先点击右上角「下载识别模型」',true);return;}await startJob('transcribe');}));
$('rules').addEventListener('click',protect(()=>startJob('rules')));
$('create-proxy').addEventListener('click',protect(()=>startJob('proxy')));
$('render').addEventListener('click',protect(()=>startJob('render')));
$('draft').addEventListener('click',protect(async()=>{if(workspace==='jianying'&&!appState.settings.draft_root){openSettings();message('请先填写剪映 5.9 的草稿目录');return;}await startJob(workspace==='pr'?'premiere':'draft',{subtitles:$('include-subtitles').checked,mode:$('draft-mode').value});}));
$('delete-selection').addEventListener('click',protect(async()=>{if(!selection.length)return;const tokens=project.transcript.tokens,lo=Math.min(...selection),hi=Math.max(...selection);await mutate({action:'add',start:tokens[lo].start,end:tokens[hi].end,text:tokens.slice(lo,hi+1).map(t=>t.text).join(''),reason:'人工选择文稿区间'});}));
$('clear-selection').addEventListener('click',()=>{selection=[];updateSelection();});
$('manual-add').addEventListener('click',protect(()=>mutate({action:'add',start:Math.round(Number($('manual-start').value)*1000),end:Math.round(Number($('manual-end').value)*1000),review_action:$('manual-category').value,reason:'人工指定分轨归类'})));
$('use-current').addEventListener('click',()=>{const time=video.currentTime||0;$('manual-start').value=time.toFixed(3);$('manual-end').value=Math.min(time+1,(project?.media.duration||1000)/1000).toFixed(3);});
$('restore-all').addEventListener('click',protect(()=>mutate({action:'restore_all'})));
function openSettings(){
  const s=appState.settings;$('provider').value=s.provider;$('model').value=s.model;$('api-key').value='';$('clear-key').checked=false;
  $('key-state').textContent=s.has_api_key?'本次会话已配置':'尚未配置';
  $('draft-root').value=s.draft_root||'';$('silence-threshold').value=s.silence_threshold;$('silence-keep').value=s.silence_keep;
  $('draft-roots').innerHTML=appState.draft_suggestions.map(path=>`<option value="${escapeHTML(path)}"></option>`).join('');
  $('settings-title').textContent=workspace==='pr'?'模型与 PR 设置':workspace==='ae'?'模型设置':'模型与剪映设置';
  $('jianying-root-label').hidden=workspace!=='jianying';$('jianying-root-hint').hidden=workspace!=='jianying';$('pr-install-note').hidden=workspace!=='pr';
  $('settings-dialog').showModal();
}
$('settings-open').addEventListener('click',openSettings);
$('settings-close').addEventListener('click',()=>{$('api-key').value='';$('settings-dialog').close();});
$('settings-dialog').addEventListener('cancel',()=>{$('api-key').value='';});
$('provider').addEventListener('change',()=>{$('model').value=$('provider').value==='deepseek'?'deepseek-chat':'';$('api-key').value='';$('key-state').textContent='切换服务商后需重新填写 Key';});
$('settings-form').addEventListener('submit',protect(async event=>{
  event.preventDefault();const result=await api('/api/settings',{provider:$('provider').value,model:$('model').value,api_key:$('api-key').value,clear_key:$('clear-key').checked,draft_root:$('draft-root').value,silence_threshold:Number($('silence-threshold').value),silence_keep:Number($('silence-keep').value)});
  appState={...result,csrf_token:appState.csrf_token};$('api-key').value='';$('settings-dialog').close();message('设置已保存，Key 仅在本次服务进程内有效');renderSidebar();
}));
function openEditorial(task){
  if(busy||!project)return;
  if(project.diarization?.status!=='done'||project.review_confirmed!==true){message('请先本地识别说话人、人工修正人物与分句，并勾选复核确认',true);return;}
  if(task==='analyze'&&!project.transcript?.tokens?.length){message('请先完成中文转录与人物识别',true);return;}
  if(!appState.settings.has_api_key){openSettings();message('请先填写 API Key');return;}
  aiTask=task;$('ai-dialog-title').textContent=task==='prepare_editorial'?'识别人物并 AI 校正整句':'上传已复核文稿：AI 拆句与校正';
  $('ai-task-note').hidden=false;$('ai-upload-description').textContent='将字词 ID、原始时间戳、转录文字和匿名人物标签发送给';
  $('ai-snapshot').textContent=($('compression-enabled').checked?`随后综合整段视频全部文稿，目标保留约 ${$('retention').value}%。`:'不启用信息浓缩，普通内容整句保留。')+(task==='prepare_editorial'?' 首先自动执行本地文稿与人物识别。':'');
  $('ai-provider').textContent=appState.settings.provider==='deepseek'?'DeepSeek':'OpenAI';$('ai-dialog').showModal();
}
$('analyze').addEventListener('click',()=>openEditorial('analyze'));
for(const id of ['ai-close','ai-cancel'])$(id).addEventListener('click',()=> {summarySnapshot='';$('ai-dialog').close();});
$('ai-confirm').addEventListener('click',protect(async()=>{$('ai-dialog').close();try{if(aiTask==='summarize')await startJob('summarize',{consent:true,text:summarySnapshot});else await startJob(aiTask,{consent:true,speakers:Number($('speaker-count').value)});}finally{summarySnapshot='';}}));
function loadWorkflow(){
  const c=project.workflow||{};
  $('manual-cut').checked=c.manual_cut||false;
  $('compression-enabled').checked=c.compression_enabled||false;
  $('retention').value=c.retention??70;
  $('direct-delete').checked=c.direct_delete||false;
  $('draft-name').value=c.draft_name||'';
  $('speaker-count').value=c.speakers??-1;
  $('include-subtitles').checked=c.subtitles??true;
  $('draft-mode').value=c.draft_mode||'review';
  renderRetention();
}
function renderRetention(){
  $('retention-value').textContent=`${$('retention').value}%`;
  $('retention').disabled=busy||!$('compression-enabled').checked;
  $('draft-mode').disabled=busy||$('direct-delete').checked;
  $('draft').textContent=workspace==='pr'?($('direct-delete').checked?'生成 PR 合并工程包 ↗':'生成 PR 工程包 ↗'):($('direct-delete').checked?'生成合并草稿 ↗':'生成剪映草稿 ↗');
  const r=project?.retention_report;
  $('retention-report').textContent=r?.actual!=null?`整段视频预计保留文稿 ${r.actual}%（${r.kept_characters}/${r.total_characters} 字）；${r.needs_reanalysis?'目标已变更，请重新提交 AI 审核。':r.off_target?'实际值偏离目标超过 10 个百分点，请复核或重新分析。':'目标为近似值，不强行删除关键信息。'}`:'完成识别和分析后显示预计保留比例。';
  $('export-note').textContent=$('direct-delete').checked?'直接删除整个建议删除轨道（包含未勾选建议），合拢剩余视频与字幕。JSON、SRT、MP4 和草稿使用同一时间映射。':'分轨草稿保持原片位置与声音；常规紧凑导出只删除勾选区间。';
  if($('manual-cut').checked)$('export-note').textContent='直接使用当前人工复核分句时间戳切开画面，无需上传 AI；保留人工归类和删减，忽略自动建议。';
  if(workspace==='pr')$('export-note').textContent='PR 输出 XML 工程交换包，切点按帧取整；导入后另存 .prproj。勾选字幕会添加独立透明字幕画面轨，导入即显示；改字可使用同包 SRT，字幕未启用删除联动。'+($('direct-delete').checked?' 已启用删除建议轨道并合并。':' 默认保留完整分轨供审核。');
}
async function saveWorkflow(){
  await mutate({action:'config',config:{manual_cut:$('manual-cut').checked,compression_enabled:$('compression-enabled').checked,retention:Number($('retention').value),direct_delete:$('direct-delete').checked,draft_name:$('draft-name').value,speakers:Number($('speaker-count').value),subtitles:$('include-subtitles').checked,draft_mode:$('draft-mode').value}});
  renderRetention();
}
for(const id of ['manual-cut','compression-enabled','retention','direct-delete','draft-name','speaker-count','include-subtitles','draft-mode'])$(id).addEventListener('change',protect(async()=>{try{await saveWorkflow();}catch(error){loadWorkflow();throw error;}}));
$('retention').addEventListener('input',()=>{$('retention-value').textContent=`${$('retention').value}%`;});
$('select-all').addEventListener('click',protect(()=>mutate({action:'select_all',accepted:true})));
$('deselect-all').addEventListener('click',protect(()=>mutate({action:'select_all',accepted:false})));
$('prepare').addEventListener('click',protect(()=>startJob('prepare',{speakers:Number($('speaker-count').value)})));
$('review-confirmed').addEventListener('change',protect(async()=>{await mutate({action:'confirm_review',confirmed:$('review-confirmed').checked});}));
for(const [id,split] of [['split-sentence',true],['join-sentence',false]])$(id).addEventListener('click',protect(async()=>{if(!selection.length)return;const end=Math.max(...selection);await mutate({action:'sentence_boundary',token_id:project.transcript.tokens[end].id,split});message(split?'已设定人工分句，请重新确认复核':'已取消该处断句，请重新确认复核');}));
function renderWorkspaceLabels(){
  const pr=workspace==='pr',ae=workspace==='ae';
  document.querySelectorAll('[data-space]').forEach(n=>{n.classList.toggle('selected',n.dataset.space===workspace);n.setAttribute('aria-pressed',String(n.dataset.space===workspace));});
  $('workspace-label').textContent=ae?'AE · 功能待开放':pr?'PR 2026 · 工程制作区':'剪映 5.9 工作流';
  $('summary-load').disabled=busy||!project||ae;
  $('projects').hidden=ae;$('new-project').disabled=busy||ae;
  $('settings-open').title=pr?'模型与 PR 设置':ae?'模型设置':'模型与剪映设置';
  $('settings-label').textContent=$('settings-open').title;
  $('workspace-description').textContent=pr?'识别中文口播，试听每一个切点，把确认后的方案带进 Premiere Pro。':ae?'AE 工程功能预留；可先使用 AI 提炼主题整理文稿。':'识别中文口播，试听每一个切点，把确认后的方案带进剪映。';
  $('workspace-feature').textContent=pr?'03 / 继续在 PR 精修':'03 / 继续在剪映精修';
  document.querySelector('.steps li:last-child').innerHTML=pr?'<b>04</b> 生成 PR 工程':'<b>04</b> 生成剪映草稿';
  if(project&&!ae){
    $('draft-name-label').textContent=pr?'PR 工程名称':'剪映草稿名称';
    $('draft-mode-label').textContent=pr?'工程模式':'草稿模式';
    $('export-heading').textContent=pr?'把剪辑方案带到 Premiere Pro':'把分轨方案带到剪映';
    document.querySelector('.steps li:last-child').innerHTML=pr?'<b>04</b> 生成 PR 工程':'<b>04</b> 生成剪映草稿';
    renderRetention();

  }
  $('gap-panel').hidden=ae;
  $('gap-instructions').textContent=pr?'在 PR 保存精剪结果，选中该序列 → 文件 → 导出 → Final Cut Pro XML。填写导出 XML 路径，合拢后导入新的 timeline.xml。支持本工具生成的透明图片字幕轨；PR 原生字幕轨需另行处理。':'在剪映保存并返回首页，填写精剪草稿文件夹或 draft_content.json 的路径。合拢后在首页刷新并打开名称含“精剪合拢”的新草稿。';
  $('gap-path-label').textContent=pr?'精剪后导出的 XML 完整路径':'精剪后保存的剪映草稿文件夹';
  $('gap-path').placeholder=pr?'例如 D:\\精剪工程\\精剪序列.xml':'例如 D:\\JianyingPro Drafts\\我的精剪草稿';
  $('gap-path').value='';$('gap-result').hidden=true;
  $('ae-placeholder').hidden=!ae;
  document.querySelector('.steps').hidden=ae;
  if(ae){$('import-panel').hidden=true;$('editor').hidden=true;$('project-name').textContent=KouboI18n.translate('AE 占位区');}
}
async function switchWorkspace(next){
  if(busy||editing)throw new Error('当前任务执行中，完成后可切换区块');
  spaceViews[workspace]={id:project?.id,source:$('summary-source').value,result:$('summary-result').value};
  workspace=next;project=null;video.pause();video.removeAttribute('src');selection=[];audition=null;
  history.replaceState(null,'',`/?workspace=${next}&lang=${KouboI18n.language}`);
  $('summary-source').value=spaceViews[next]?.source||'';$('summary-result').value=spaceViews[next]?.result||'';
  $('editor').hidden=true;$('import-panel').hidden=next==='ae';$('export-result').hidden=true;
  $('project-name').textContent=KouboI18n.translate(next==='pr'?'新建 PR 工程':'新建粗剪');
  await refreshState();
  if(next!=='ae'&&spaceViews[next]?.id)await openProject(spaceViews[next].id);
  renderWorkspaceLabels();
}
for(const n of document.querySelectorAll('[data-space]'))n.addEventListener('click',protect(()=>switchWorkspace(n.dataset.space)));
$('summary-load').addEventListener('click',()=>{
  if(!project?.transcript?.tokens?.length){message('请先识别当前视频文稿',true);return;}
  const groups=[];let speaker;
  for(const t of project.transcript.tokens){const sp=t.speaker||'unknown';if(sp!==speaker||!groups.length){groups.push(`人物 ${sp}：`);speaker=sp;}groups[groups.length-1]+=(t.corrected_text??t.text);}
  const text=groups.join('\n');if(text.length>20000){message('当前文稿超过 20,000 字符，请分段粘贴后提炼',true);return;}
  $('summary-source').value=text;message('已载入当前文稿，带匿名人物标签；可在左侧编辑后提交');
});
$('summary-analyze').addEventListener('click',()=>{
  if(busy||editing)return;
  const text=$('summary-source').value.trim();if(!text){message('请先粘贴或载入文稿',true);return;}
  if(!appState.settings.has_api_key){openSettings();message('请先填写 API Key');return;}
  aiTask='summarize';summarySnapshot=text;
  $('ai-dialog-title').textContent='提炼文稿主题与标题';$('ai-task-note').hidden=true;$('ai-upload-description').textContent='将当前原文参考框中的文字发送给';
  $('ai-provider').textContent=appState.settings.provider==='deepseek'?'DeepSeek':'OpenAI';
  $('ai-snapshot').textContent=`本次提交 ${text.length} 字符；返回建议标题、主题、精简主体与要点，不修改剪辑。`;
  $('ai-dialog').showModal();
});
$('summary-copy').addEventListener('click',protect(async()=>{
  if(!$('summary-result').value.trim()){message('尚无可复制的反馈',true);return;}
  try{await navigator.clipboard.writeText($('summary-result').value);message('已复制修改后的反馈');}
  catch{$('summary-result').focus();$('summary-result').select();message('已选中反馈，请按 Ctrl+C 复制');}
}));
$('gap-close').addEventListener('click',protect(async()=>{
  if(busy)return;
  const path=$('gap-path').value.trim();if(!path)throw new Error('请先填写已保存草稿或导出 XML 的本机路径');
  setBusy(true);$('job-message').textContent='读取精剪工程，计算视频、音频和字幕的共同移动量…';$('job-progress').style.width='15%';$('job-percent').textContent='';
  try{
    const r=await api('/api/gap-close',{path});
    const divisor=r.unit==='frames'?r.fps:1000000;
    $('gap-result').innerHTML=`<h3>已生成精剪合拢副本</h3><p>合拢 ${r.gap_count} 处空隙，缩短 ${(r.removed_duration/divisor).toFixed(2)} 秒；结果时长 ${(r.duration/divisor).toFixed(2)} 秒。</p><p>${escapeHTML(r.note)}</p><p class="hint">${escapeHTML(r.path)}</p>${r.download?`<a class="button small dark" href="${escapeHTML(r.download)}">下载合拢工程包</a> `:''}<a class="button small ghost" href="${escapeHTML(r.report)}">下载时间映射报告</a>`;
    $('gap-result').hidden=false;message('精剪空隙已合拢，字幕按同一时间映射移动');
  }finally{setBusy(false);}
}));
$('language-toggle').textContent=KouboI18n.language==='en'?'中文':'English';
$('language-toggle').addEventListener('click',()=>{
  if(busy||editing){message('请等待当前任务完成',true);return;}
  const next=KouboI18n.language==='en'?'zh':'en';localStorage.setItem('koubo-language',next);
  const u=new URL(location.href);u.searchParams.set('lang',next);location.assign(u);
});
renderWorkspaceLabels();
refreshState().catch(error=>message(`无法连接本地服务：${error.message}`,true));

if(!project)$('project-name').textContent=KouboI18n.translate($('project-name').textContent);
