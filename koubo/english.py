"""English-only, offline Zipformer recognition; models never share Chinese caches."""
import hashlib
import json
import os
import urllib.request
from pathlib import Path

MODEL_ID = 'sherpa-onnx-zipformer-small-en-2023-06-26'
REVISION = 'e8add5377a6cb7b629b5a0e08d6afe7a73442814'
FILES = ('encoder-epoch-99-avg-1.int8.onnx', 'decoder-epoch-99-avg-1.int8.onnx',
         'joiner-epoch-99-avg-1.int8.onnx', 'tokens.txt')
BASE = f'https://huggingface.co/csukuangfj/{MODEL_ID}/resolve/{REVISION}'


def ready(directory):
    return all((Path(directory)/name).is_file() and (Path(directory)/name).stat().st_size >
               (1000 if name.endswith('.txt') else 10000) for name in FILES)


def download(directory, progress=lambda *args: None):
    directory = Path(directory);directory.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for i, name in enumerate(FILES):
        dest = directory/name
        if not dest.is_file() or dest.stat().st_size <= (1000 if name.endswith('.txt') else 10000):
            part = dest.with_suffix(dest.suffix+'.part')
            request = urllib.request.Request(f'{BASE}/{name}', headers={'User-Agent':'KouboCut/0.6'})
            with urllib.request.urlopen(request, timeout=90) as response, part.open('wb') as output:
                total = int(response.headers.get('Content-Length',0));count = 0
                while block := response.read(1024*1024):
                    count += len(block);output.write(block)
                    progress(f'Downloading English model: {name} ({count/1048576:.1f} MB)',
                             round((i+(count/total if total else 0))/len(FILES)*100))
                if total and total != count:
                    raise ValueError('English model download is incomplete. Please retry.')
            os.replace(part,dest)
        digest = hashlib.sha256()
        with dest.open('rb') as stream:
            while block := stream.read(1024*1024):digest.update(block)
        manifest[name] = {'bytes':dest.stat().st_size,'sha256':digest.hexdigest()}
    (directory/'download-info.json').write_text(json.dumps({'model':MODEL_ID,'revision':REVISION,
        'license':'Apache-2.0','files':manifest},indent=2),encoding='utf-8')
    progress('English model is ready',100)


def transcribe(audio, media, silences, model_dir, progress):
    import sherpa_onnx
    from .media import read_audio, recognition_chunks
    directory = Path(model_dir)
    if not ready(directory):
        raise ValueError('English model is not ready. Click Download speech model first.')
    progress('Loading local English Zipformer model',5)
    recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(directory/FILES[0]),decoder=str(directory/FILES[1]),joiner=str(directory/FILES[2]),
        tokens=str(directory/FILES[3]),num_threads=min(6,max(1,(os.cpu_count() or 4)//2)),
        provider='cpu',debug=False,decoding_method='greedy_search')
    samples,rate = read_audio(audio);chunks = recognition_chunks(media['duration'],silences)
    tokens,segments,warnings = [],[],[]
    for n,(start,end) in enumerate(chunks):
        progress(f'Transcribing English chunk {n+1}/{len(chunks)}',10+round(85*n/len(chunks)))
        signal = samples[round(start*rate/1000):round(end*rate/1000)]
        if not len(signal) or max(abs(signal)) < .001:continue
        stream = recognizer.create_stream();stream.accept_waveform(rate,signal);recognizer.decode_stream(stream)
        result = stream.result
        if not result.text.strip():continue
        words = timed_words(list(result.tokens),list(result.timestamps),start,end)
        if not words:
            words = [{'text':result.text.strip(),'start':start,'end':end,'aligned':False,'timing':'segment_only'}]
            warnings.append(f'Chunk {n+1}: word timestamps unavailable; review the whole chunk.')
        for word in words:
            word['start'] = max(word['start'], tokens[-1]['end'] if tokens else 0)
            if word['end'] <= word['start']:continue
            word['id'] = f't{len(tokens)+1:06d}'
            if tokens and not word['text'].startswith(' '):word['text'] = ' '+word['text']
            tokens.append(word)
        segments.append({'id':f's{len(segments)+1:04d}','start':start,'end':end,'text':result.text.strip()})
    if not tokens:raise ValueError('No English speech detected. Check the language and audio track.')
    return {'engine':'sherpa-onnx/'+MODEL_ID+'-int8','language':'en','tokens':tokens,'segments':segments,
            'warnings':warnings,'timing_note':'Model word starts; word ends are estimates. Audition every cut.'}


def timed_words(pieces, times, start, end):
    if len(pieces) != len(times) or not times:return []
    words = [];boundary = False
    for i,piece in enumerate(pieces):
        new = boundary or piece.startswith(('▁',' '));text = piece.replace('▁',' ').strip()
        boundary = new and not text
        if not text or text.startswith('<'):continue
        a = max(start,min(end-1,start+round(times[i]*1000)))
        next_start = start+round(times[i+1]*1000) if i+1<len(times) else end
        b = min(end,next_start,a+(500 if i+1==len(times) else 700))
        if b <= a:continue
        boundary = False
        if words and not new:
            words[-1]['text'] += text;words[-1]['end'] = b
        else:
            words.append({'text':(' ' if words else '')+text,'start':a,'end':b,
                          'aligned':True,'timing':'model_start_estimated_end'})
    return words
