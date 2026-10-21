import json
from pathlib import Path
from html.parser import HTMLParser
import re

import httpx
import pytest
from test_server import server
from koubo import editorial,english
from koubo.ai import summarize
from koubo.sentences import preview_breaks


def test_english_subwords_are_one_timed_word():
    words=english.timed_words(['▁HEL','LO','▁DON',"'",'T','▁STOP'],[.1,.2,.4,.5,.6,.9],1000,2400)
    assert [w['text'] for w in words]==['HELLO'," DON'T",' STOP']
    assert words[0]['start']==1100 and words[0]['end']==1400
    assert words[1]['start']==1400 and words[1]['end']==1900
    assert english.timed_words(['▁HELLO'],[],0,1000)==[]


def test_languages_use_different_models_projects_and_jobs(server):
    service,client=server
    zh=client.get('/api/state').json();en=client.get('/api/state?lang=en').json()
    assert zh['language']=='zh' and en['language']=='en'
    assert 'english' in en['data_directory'] and en['data_directory']!=zh['data_directory']
    # The imported media may be identical; caches must still remain isolated.
    eng=__import__('koubo.service',fromlist=['Service']).Service(service.directory/'english',shared=service,language='en')
    assert eng.model_dir.name==english.MODEL_ID and eng.model_dir!=service.model_dir
    assert client.get('/api/state?lang=fr').status_code==400
    assert client.get('/i18n.js').status_code==200
    assert client.get('/favicon.ico').content[:4]==b'\x00\x00\x01\x00'


def en_project():
    return {'language':'en','transcript':{'tokens':[
        {'id':'a','text':'Hello','speaker':'A','start':0,'end':300},
        {'id':'b','text':' um','speaker':'A','start':400,'end':700},
        {'id':'c','text':' friend','speaker':'A','start':800,'end':1100}]}}


def test_english_filler_validation_and_word_spacing():
    p=en_project()
    data={'corrections':[{'token_id':'c','text':'friends,'}],
          'sentences':[{'from_token':'a','to_token':'c'}],
          'fillers':[{'from_token':'b','to_token':'b','reason':'meaningless hesitation'}]}
    result=editorial.validate_polish(data,p)
    assert result['corrections']['c']==' friends,'
    assert result['sentences'][0]['text']=='Hello um friends,'
    assert len(result['fillers'])==1
    data['fillers'][0]['from_token']='c';data['fillers'][0]['to_token']='c'
    with pytest.raises(ValueError):editorial.validate_polish(data,p)


def test_english_preview_counts_words_instead_of_characters():
    p=en_project();p['transcript']['tokens']=[{'id':str(i),'text':' extraordinarily','speaker':'A','start':i*300,'end':i*300+290} for i in range(14)]
    assert preview_breaks(p)==['13']


def test_english_summary_prompt_and_labels():
    def handler(request):
        body=json.loads(request.content)
        assert 'English JSON' in body['messages'][0]['content']
        data={'title':'A simple title','topic':'An example','concise':'A short summary','key_points':['A fact']}
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(data)}}]})
    result=summarize('An example transcript',{'language':'en','provider':'deepseek','model':'mock','api_key':'mock'},httpx.MockTransport(handler))
    assert result['text'].startswith('Suggested title\n')


def test_all_static_ui_text_has_english_translation():
    root=Path(__file__).parents[1]/'static'
    script=(root/'i18n.js').read_text(encoding='utf-8')
    keys={line.split(' | ',1)[0] for line in script.splitlines() if ' | ' in line}
    strings=[]
    class Inventory(HTMLParser):
        def handle_data(self,data):
            if re.search('[\u4e00-\u9fff]',data):strings.append(data.strip())
        def handle_starttag(self,tag,attributes):
            for name,value in attributes:
                if name in ('title','placeholder','aria-label') and value and re.search('[\u4e00-\u9fff]',value):strings.append(value)
    Inventory().feed((root/'index.html').read_text(encoding='utf-8'))
    assert not [text for text in strings if text not in keys]


def test_english_standalone_word_boundary():
    words=english.timed_words(['▁HELLO','▁','WORLD'],[.1,.3,.4],0,1000)
    assert [x['text'] for x in words]==['HELLO',' WORLD']
