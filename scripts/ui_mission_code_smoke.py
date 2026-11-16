"""Actual native Ollama FILE stream -> mission -> live editor -> approval/save -> paused recovery."""
import argparse,asyncio,json,os,sys,tempfile,threading,time
from pathlib import Path


def run(config):
    from playwright.sync_api import sync_playwright,expect
    import httpx,uvicorn
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
    with tempfile.TemporaryDirectory(prefix='barq-live-ui-') as folder:
        temp=Path(folder);project=temp/'project';project.mkdir();(project/'live-app').mkdir();file=project/'live-app/storage.py'
        os.environ['AI_ROUTER_DATA_DIR']=str(temp/'state')
        import api,core.secrets
        from router.config import Config,Provider,Model
        from router.engine import Engine
        from brain.coordinator import Brain
        from brain.state import TaskStore
        from desktop import free_port
        from mission.tracking import start
        from mission.engine import seed_manifest
        goal='ابني برنامج Windows اسمه Live App'
        start(str(project),'live-app','desktop_python',goal,['main.py'])
        seed_manifest(str(project),'live-app')
        engine=Engine(Config(providers=[Provider(name='ollama',kind='local',base_url='http://127.0.0.1:11434/v1',
            models=[Model(name='qwen3:4b',strengths=['coding'],context_window=32768)])]),cache_path=str(temp/'cache.sqlite3'))
        api.brain=Brain(engine,TaskStore(temp/'brain.sqlite3'))
        gate=threading.Event();sent=threading.Event();requests=[]
        prefix='### FILE: live-app/storage.py\n```python\nimport json\n'
        suffix='\ndef load(path):\n    return json.loads(path.read_text()) if path.exists() else {}\n```'
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield (json.dumps({'message':{'content':prefix},'done':False})+'\n').encode()
                sent.set()
                while not gate.is_set():await asyncio.sleep(.02)
                yield (json.dumps({'message':{'content':suffix},'done':False})+'\n').encode()
                yield b'{"done":true,"done_reason":"stop"}\n'
        async def upstream(request):
            if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':'qwen3:4b'}]})
            payload=json.loads(request.content);requests.append(payload)
            assert payload['stream'] is True and payload['think'] is False
            assert payload['model']=='qwen3:4b'
            if len(requests)==1:return httpx.Response(200,headers={'content-type':'application/x-ndjson'},stream=Stream())
            # Truncated next-file output must pause, never save incomplete code.
            return httpx.Response(200,headers={'content-type':'application/x-ndjson'},content=
                (json.dumps({'message':{'content':'### FILE: live-app/main.py\n```python\ndef broken('},'done':True})+'\n').encode())
        real_client=httpx.AsyncClient
        def client(**kwargs):return real_client(**{**kwargs,'transport':httpx.MockTransport(upstream),'trust_env':False})
        httpx.AsyncClient=client
        port=free_port();server=uvicorn.Server(uvicorn.Config(api.app,host='127.0.0.1',port=port,log_level='error'))
        thread=threading.Thread(target=server.run,daemon=True);thread.start();errors=[];calls=[]
        try:
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            assert server.started
            with sync_playwright() as runtime:
                browser=runtime.chromium.launch(headless=True,executable_path=config['executablePath'],args=config.get('args',[]))
                context=browser.new_context(viewport={'width':1440,'height':1000})
                state={'language':'ar','theme':'dark','workspace':str(project),'activeId':'live','selectedModel':'ollama/qwen3:4b',
                    'chats':[{'id':'live','title':'كود مباشر','createdAt':1,'updatedAt':1,'messages':[]}]}
                context.add_init_script('localStorage.setItem("ai-router-premium-ui-v2",'+json.dumps(json.dumps({'state':state,'version':0}))+');')
                def route(request_route):
                    path=request_route.request.url.split('/v1/',1)[-1].split('?',1)[0]
                    if path.startswith(('brain/','agent/','studio/','workspace/','coding/')):
                        calls.append(path);request_route.continue_();return
                    fixtures={'router/models':{'models':[]},'router/providers':{'providers':[]},'conversations':{'conversations':[]},
                        'router/connectivity':{'mode':'auto','cloud_connection':'not_checked_or_restored','ollama':{'enabled':False,'reachable':False,'models':[]}},
                        'computer/status':{'supported':False,'status':'not_supported'}}
                    request_route.fulfill(status=200,content_type='application/json',body=json.dumps(fixtures.get(path,{})))
                context.route('**/v1/**',route)
                page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{port}',wait_until='networkidle')
                page.locator('#chatComposer').fill(goal);page.locator('#chatComposer').press('Enter')
                studio=page.get_by_role('region',name='مساحة برمجة برق')
                code=studio.get_by_test_id('agent-live-code')
                expect(code).to_have_text('import json\n',timeout=15000)
                assert sent.is_set() and not gate.is_set() and not file.exists()
                assert calls.count('agent/execute')==0 and calls.count('workspace/edit/apply')==0
                expect(studio.get_by_role('button',name='مراجعة الخطوة الحالية',exact=True)).to_be_disabled()
                gate.set()
                approval=page.get_by_role('dialog',name='الموافقة على الخطوة',exact=True);approval.wait_for(state='visible')
                approval.get_by_role('button',name='لاحقًا',exact=True).click()
                expect(code).to_have_text('import json\n\ndef load(path):\n    return json.loads(path.read_text()) if path.exists() else {}\n')
                studio.get_by_role('button',name='مراجعة الخطوة الحالية',exact=True).click()
                approval.get_by_role('button',name='موافقة وتنفيذ',exact=True).click()
                save=page.get_by_role('dialog',name='مراجعة التعديل وحفظه',exact=True);save.wait_for(state='visible')
                assert not file.exists()
                save.get_by_role('button',name='موافقة وحفظ',exact=True).click()
                page.wait_for_function("async () => (await (await fetch('/v1/brain/state?conversation_id=live')).json()).task?.status === 'paused'",timeout=15000)
                page.wait_for_function("() => JSON.parse(localStorage.getItem('ai-router-premium-ui-v2')).state.chats.find(c=>c.id==='live').messages.some(m=>m.agentTask?.status==='paused')",timeout=15000)
                assert file.read_text()=='import json\n\ndef load(path):\n    return json.loads(path.read_text()) if path.exists() else {}\n'
                page.wait_for_function("() => JSON.parse(localStorage.getItem('ai-router-premium-ui-v2')).state.chats.find(c=>c.id==='live').messages.some(m=>m.agentTask?.summary==='توليد الملف التالي متوقف؛ باقي ملفات المهمة محفوظة')",timeout=10000)
                saved_state=page.evaluate("JSON.parse(localStorage.getItem('ai-router-premium-ui-v2')).state")
                latest=next(m['agentTask'] for m in reversed(saved_state['chats'][0]['messages']) if m.get('agentTask'))
                assert latest['status']=='paused' and not latest.get('phase') and latest.get('retryId'), latest
                assert latest.get('summary')=='توليد الملف التالي متوقف؛ باقي ملفات المهمة محفوظة'
                studio.get_by_role('button',name='الرجوع للمحادثة',exact=True).click()
                reason=page.get_by_text('سبب التوقف والمحاولة الأخيرة',exact=True).last
                expect(reason).to_be_visible();reason.click()
                expect(page.get_by_text('Incomplete or wrong target FILE block',exact=False).last).to_be_visible()
                assert len(requests)==3
                assert not (project/'live-app/main.py').exists()
                assert all('ollama' in req['model'] or req['model']=='qwen3:4b' for req in requests)
                assert calls.count('agent/execute')==1 and calls.count('workspace/edit/apply')==1
                assert not errors,errors
                context.close();browser.close()
            return {'status':'passed','real_ollama_file_code_visible_before_completion':True,'automatic_live_tab':True,
                    'partial_code_cannot_execute':True,'separate_approved_save':True,'no_duplicate_writes':True,'failed_next_file_pauses_and_clears_spinner':True,
                    'note':'Actual Engine, HTTP adapter, browser, API and disk writes; controlled native Ollama NDJSON, not live external inference or native Windows.'}
        finally:gate.set();httpx.AsyncClient=real_client;server.should_exit=True;thread.join(timeout=10);assert not thread.is_alive()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--browser-config',required=True);parser.add_argument('--output')
    args=parser.parse_args();result=run(json.loads(Path(args.browser_config).read_text()));text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:Path(args.output).write_text(text)
    print(text)
