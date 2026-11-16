"""Real React/FastAPI/Engine/HTTP-adapter smoke; provider HTTP replies are controlled.

Runs in temporary user data and a temporary project. Never calls live providers
or approves project writes. Requires Playwright and an installed Chromium.
"""
import argparse,json,os,sys,tempfile,threading,time
from pathlib import Path


def run(browser_config=None):
    from playwright.sync_api import sync_playwright
    import httpx,uvicorn
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    with tempfile.TemporaryDirectory(prefix='barq-command-ui-') as folder:
        temp=Path(folder);project=temp/'project';project.mkdir()
        source=project/'app.py';source.write_text("COLOR = 'blue'\n")
        os.environ['AI_ROUTER_DATA_DIR']=str(temp/'state')
        import api,core.secrets
        from router.config import Config,Provider,Model
        from router.engine import Engine
        from brain.coordinator import Brain
        from brain.state import TaskStore
        from desktop import free_port
        core.secrets.get=lambda name:'test-not-a-live-key'
        groq=Provider(name='groq',base_url='https://api.groq.com/openai/v1',api_key_env='GROQ_API_KEY',
            models=[Model(name='openai/gpt-oss-120b',free=True,strengths=['reasoning','coding'],context_window=32000)])
        engine=Engine(Config(providers=[groq]),cache_path=str(temp/'cache.sqlite3'))
        db=temp/'brain.sqlite3';api.brain=Brain(engine,TaskStore(db))
        provider_calls=[]
        def upstream(request):
            provider_calls.append(request.url.host)
            if request.url.host=='api.groq.com':return httpx.Response(401,json={'error':'do not expose raw upstream body'})
            messages=json.loads(request.content)['messages']
            if messages[0]['content'].startswith('You classify'):
                output={'kind':'coding','goal':'Change COLOR in app.py to red'}
            else:
                output={'reason':'Propose the requested edit','steps':[{'tool':'code_replace','args':{
                    'path':'app.py','before':"COLOR = 'blue'",'after':"COLOR = 'red'"}}],'answer':'التعديل جاهز للموافقة.'}
            return httpx.Response(200,json={'choices':[{'message':{'content':'```json\n'+json.dumps(output)+'\n```'}}]})
        real_client=httpx.AsyncClient
        def client(**kwargs):
            kwargs.update(transport=httpx.MockTransport(upstream),trust_env=False)
            return real_client(**kwargs)
        httpx.AsyncClient=client
        port=free_port();server=uvicorn.Server(uvicorn.Config(api.app,host='127.0.0.1',port=port,log_level='error'))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        try:
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            assert server.started
            calls=[];errors=[];statuses=[]
            with sync_playwright() as runtime:
                config=browser_config or {}
                launch={'headless':True}
                if config.get('executablePath'):launch.update(executable_path=config['executablePath'],args=config.get('args',[]))
                browser=runtime.chromium.launch(**launch)
                context=browser.new_context(viewport={'width':1440,'height':900})
                state={'language':'ar','theme':'dark','sidebarCollapsed':False,'activeId':'command-ui','workspace':str(project),
                    'chats':[{'id':'command-ui','title':'اختبار الأوامر','createdAt':1,'updatedAt':1,'messages':[]}]}
                context.add_init_script('if(!localStorage.getItem("ai-router-premium-ui-v2"))localStorage.setItem("ai-router-premium-ui-v2",'+json.dumps(json.dumps({'state':state,'version':0}))+');')
                def api_route(route):
                    path=route.request.url.split('/v1/',1)[-1].split('?',1)[0]
                    if path.startswith(('brain/','agent/','studio/')) or (path=='workspace/file' and route.request.method=='GET'):
                        calls.append(path);route.continue_();return
                    fixtures={'router/models':{'models':[]},'router/providers':{'providers':[]},
                        'router/connectivity':{'mode':'auto','cloud_connection':'not_checked_or_restored','ollama':{'enabled':False,'reachable':False,'models':[]}},
                        'conversations':{'conversations':[]},'computer/status':{'supported':False,'status':'not_supported'}}
                    calls.append(path)
                    route.fulfill(status=200,content_type='application/json',body=json.dumps(fixtures.get(path,{})))
                context.route('**/v1/**',api_route)
                page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('response',lambda response:statuses.append(response.status) if '/v1/' in response.url else None)
                page.goto(f'http://127.0.0.1:{port}',wait_until='networkidle')
                composer=page.locator('#chatComposer');composer.wait_for(state='visible')
                text=('برق، عاوزك تبنيلي برنامج Windows كامل اسمه TOFU Desktop Buddy.\n'
                    'لا تكتفي بكتابة شرح. ممكن تضيف شاشة إعدادات وتحفظها في JSON.\n'+
                    'اطلب موافقتي على الكتابة والتشغيل ولا تدعي اكتمال البرنامج بدون اختبار. '*8).strip()
                composer.fill(text);composer.press('Enter')
                page.wait_for_function("JSON.parse(localStorage.getItem('ai-router-premium-ui-v2')).state.chats[0].messages.at(-1)?.agentTask?.status==='plan_ready'",timeout=15000)
                assert not provider_calls,'A clear new-project request should prepare locally even with all providers offline'
                assert not (project/'barq-app').exists()
                page.get_by_role('dialog',name='الموافقة على الخطوة',exact=True).get_by_role('button',name='لاحقًا',exact=True).click()
                page.locator('nav.sidebar-workspaces').first.get_by_role('button',name='المحادثة',exact=True).click()
                page.get_by_role('button',name='محادثة جديدة',exact=True).first.click()
                composer=page.locator('#chatComposer');composer.fill('محتاج الزرار ده يبقى أحمر في المشروع');composer.press('Enter')
                card=page.get_by_role('region',name='استكمال الطلب المحفوظ')
                # A labelled section is a region in Chromium accessibility.
                card.wait_for(state='visible',timeout=15000)
                assert 'مفتاح' in card.inner_text() and provider_calls==['api.groq.com']
                api.brain=Brain(engine,TaskStore(db))
                page.reload(wait_until='networkidle')
                card=page.get_by_role('region',name='استكمال الطلب المحفوظ');card.wait_for(state='visible')
                engine.config.providers.append(Provider(name='openrouter',base_url='https://openrouter.ai/api/v1',api_key_env='OPENROUTER_API_KEY',
                    models=[Model(name='openrouter/free',free=True,strengths=['reasoning','coding'],context_window=32000)]))
                card.get_by_role('button',name='استكمل نفس الطلب',exact=True).click()
                page.wait_for_function("JSON.parse(localStorage.getItem('ai-router-premium-ui-v2')).state.chats[0].messages.at(-1)?.agentTask?.status==='plan_ready'",timeout=15000)
                assert 'brain/command/retry' in calls and 'openrouter.ai' in provider_calls
                assert source.read_text()=="COLOR = 'blue'\n"
                assert not any(p in calls for p in ('agent/execute','workspace/edit/apply','launch/execute'))
                assert 422 not in statuses and not errors,errors
                context.close();browser.close()
            return {'status':'passed','cases':3,'clear_project_without_model':True,'auth_failure_rendered':True,
                'checkpoint_survived_restart_and_reload':True,'resumed_with_available_provider':True,
                'source_unchanged_without_approval':True,'provider_hosts':provider_calls,
                'note':'Actual React, FastAPI, command persistence, Engine routing and HTTP adapters. Controlled HTTP responses; no live inference or Windows claim.'}
        finally:
            httpx.AsyncClient=real_client
            server.should_exit=True;thread.join(timeout=10)
            assert not thread.is_alive()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser-config');parser.add_argument('--output')
    args=parser.parse_args();result=run(json.loads(Path(args.browser_config).read_text()) if args.browser_config else None)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:Path(args.output).write_text(text)
    print(text)
