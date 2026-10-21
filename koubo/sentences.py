"""Local readable preview, manual boundaries, and an explicit human review stage."""
def preview_breaks(project):
    tokens=project.get('transcript',{}).get('tokens',[])
    locked=set(project.get('manual_breaks',[]));joined=set(project.get('manual_joins',[]))
    if project.get('editorial'):
        return list(project.get('subtitle_breaks',[]))
    result=[];length=0
    for i,t in enumerate(tokens):
        length+=1 if project.get('language')=='en' else len(t.get('corrected_text',t['text']))
        if i==len(tokens)-1:result.append(t['id']);break
        nxt=tokens[i+1];change=t.get('speaker','unknown')!=nxt.get('speaker','unknown')
        pause=nxt['start']-t['end']
        split=change or t['id'] in locked or (t['id'] not in joined and (length>=14 or pause>=600 or (length>=7 and pause>=120) or t['text'].endswith(('，','、','。','？','！'))))
        if split:result.append(t['id']);length=0
    return result


def manual_cut_project(project):
    """Freeze the visible sentence boundaries and bypass automatic editing decisions."""
    tokens=project.get('transcript',{}).get('tokens',[])
    ends=set(preview_breaks(project));sentences=[];group=[]
    for token in tokens:
        group.append(token)
        if token['id'] in ends:
            sentences.append({'start':group[0]['start'],'end':group[-1]['end'],'to_token':group[-1]['id']})
            group=[]
    return {**project,'editing_policy':'sentences',
        'workflow':{**project.get('workflow',{}),'manual_cut':False},
        'editorial':{'sentences':sentences},'subtitle_breaks':[s['to_token'] for s in sentences],
        'candidates':[c for c in project.get('candidates',[]) if c.get('kind')=='manual' or c.get('review_action','auto')!='auto'],
        'silences':[],'diarization':{}}
