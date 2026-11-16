"""Exercise approval popups with real local tools and controlled, delayed provider HTTP."""
import argparse,asyncio,json,os,sys,tempfile,threading,time
from pathlib import Path


def run(config):
    from playwright.sync_api import sync_playwright
    import httpx,uvicorn
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
    with tempfile.TemporaryDirectory(prefix='tofu-desktop-buddyroval-ui-') as folder:
        temp=Path(folder);project=temp/'project';project.mkdir()
        os.environ['AI_ROUTER_DATA_DIR']=str(temp/'state')
        import api,core.secrets
        from router.config import Config,Provider,Model
        from router.engine import Engine
        from brain.coordinator import Brain
        from brain.state import TaskStore
        from desktop import free_port
        core.secrets.get=lambda name:'test-not-a-live-key'
        engine=Engine(Config(providers=[Provider(name='groq',base_url='https://api.groq.com/openai/v1',api_key_env='GROQ_API_KEY',
            models=[Model(name='openai/gpt-oss-120b',free=True,strengths=['coding','reasoning'],context_window=32000)])]),cache_path=str(temp/'cache.sqlite3'))
        api.brain=Brain(engine,TaskStore(temp/'brain.sqlite3'))
        gates=[threading.Event(),threading.Event()];model_calls=[]
        async def upstream(request):
            index=len(model_calls);model_calls.append(request.url.host)
            while not gates[0 if index<2 else 1].is_set():await asyncio.sleep(.01)
            if index==0:
                blueprint={'summary':'TOFU project architecture',
                    'files':[{'path':name,'purpose':'Implement '+name,'depends_on':[]} for name in ('storage.py','main.py','test_app.py','README.md')],
                    'requirements':[{'id':'R1','title':'حفظ إعدادات التطبيق','acceptance':'Restore the saved app name after restart',
                        'files':['storage.py','main.py'],'tests':['test_app.py::test_name']}]}
                content=json.dumps(blueprint,ensure_ascii=False)
            else:
                target='tofu-desktop-buddy/storage.py' if index==1 else 'tofu-desktop-buddy/main.py'
                code='APP_NAME = "TOFU Desktop Buddy"\n' if index==1 else 'from storage import APP_NAME\nprint(APP_NAME)\n'
                content='### FILE: '+target+'\n```python\n'+code+'```'
            return httpx.Response(200,json={'choices':[{'message':{'content':content}}]})
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
            calls=[];errors=[]
            with sync_playwright() as runtime:
                browser=runtime.chromium.launch(headless=True,executable_path=config['executablePath'],args=config.get('args',[]))
                context=browser.new_context(viewport={'width':1440,'height':900})
                state={'language':'ar','theme':'dark','sidebarCollapsed':False,'activeId':'approvals','workspace':str(project),
                    'chats':[{'id':'approvals','title':'اختبار الموافقة','createdAt':1,'updatedAt':1,'messages':[]}]}
                context.add_init_script('if(!localStorage.getItem("ai-router-premium-ui-v2"))localStorage.setItem("ai-router-premium-ui-v2",'+json.dumps(json.dumps({'state':state,'version':0}))+');')
                def route(request_route):
                    path=request_route.request.url.split('/v1/',1)[-1].split('?',1)[0]
                    if path.startswith(('brain/','agent/','studio/','workspace/')):
                        calls.append((path,json.loads(request_route.request.post_data or '{}')));request_route.continue_();return
                    fixtures={'router/models':{'models':[]},'router/providers':{'providers':[]},'conversations':{'conversations':[]},
                        'router/connectivity':{'mode':'auto','cloud_connection':'not_checked_or_restored','ollama':{'enabled':False,'reachable':False,'models':[]}},
                        'computer/status':{'supported':False,'status':'not_supported'}}
                    request_route.fulfill(status=200,content_type='application/json',body=json.dumps(fixtures.get(path,{})))
                context.route('**/v1/**',route)
                page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{port}',wait_until='networkidle')
                page.locator('#chatComposer').fill('ابني برنامج Windows اسمه TOFU Desktop Buddy');page.locator('#chatComposer').press('Enter')
                approval=page.get_by_role('dialog',name='الموافقة على الخطوة',exact=True)
                approval.wait_for(state='visible')
                assert not (project/'tofu-desktop-buddy').exists()
                approval.get_by_role('button',name='لاحقًا',exact=True).click()
                approval.wait_for(state='hidden')
                # The review button remains in the main chat after dismissal.
                page.locator('nav.sidebar-workspaces').first.get_by_role('button',name='المحادثة',exact=True).click()
                page.get_by_role('button',name='مراجعة الخطوة والموافقة',exact=True).click();approval.wait_for(state='visible')
                approval.get_by_role('button',name='موافقة وتنفيذ',exact=True).evaluate('(button)=>{button.click();button.click()}')
                try:approval.wait_for(state='hidden',timeout=2000)
                except Exception:
                    print(json.dumps({'calls':calls,'errors':errors,'model_calls':model_calls,'dialog':approval.inner_text(),
                        'state':page.evaluate("JSON.parse(localStorage.getItem('ai-router-premium-ui-v2')).state.chats[0]")},ensure_ascii=False),flush=True)
                    raise
                page.get_by_role('region',name='متابعة مهمة برق').get_by_text('الخطوة خلصت',exact=False).wait_for(state='visible',timeout=5000)
                assert (project/'tofu-desktop-buddy/main.py').is_file() and not gates[0].is_set()
                assert len([p for p,_ in calls if p=='agent/execute'])==1
                assert 'الخطوة خلصت' in page.get_by_role('region',name='متابعة مهمة برق').inner_text()
                gates[0].set();approval.wait_for(state='visible',timeout=10000)
                approval.get_by_role('region',name='مراجعة خطة المشروع').wait_for(state='visible')
                approval.get_by_role('button',name='موافقة وتنفيذ',exact=True).click()
                approval.get_by_text('تجهيز محتوى ملف للمراجعة',exact=True).wait_for(state='visible',timeout=10000)
                approval.get_by_role('button',name='لاحقًا',exact=True).click()
                page.evaluate('window.dispatchEvent(new Event("barq-open-workspace"))')
                studio=page.get_by_role('region',name='مساحة برمجة برق')
                studio.get_by_role('treeitem',name='main.py',exact=True).click()
                editor=studio.get_by_role('textbox',name='محرر الكود',exact=True)
                assert 'BARQ App' in editor.input_value()
                studio.get_by_role('button',name='مراجعة وموافقة',exact=True).click()
                approval.wait_for(state='visible')
                approval.get_by_role('button',name='موافقة وتنفيذ',exact=True).click()
                save=page.get_by_role('dialog',name='مراجعة التعديل وحفظه',exact=True);save.wait_for(state='visible')
                assert 'BARQ App' in (project/'tofu-desktop-buddy/main.py').read_text()
                assert 'TOFU Desktop Buddy' in save.inner_text()
                save.get_by_role('button',name='موافقة وحفظ',exact=True).click();save.wait_for(state='hidden',timeout=2000)
                from playwright.sync_api import expect
                expect(editor).to_have_value((project/'tofu-desktop-buddy/storage.py').read_text(),timeout=5000)
                assert 'TOFU Desktop Buddy' in (project/'tofu-desktop-buddy/storage.py').read_text() and not gates[1].is_set()
                assert len([p for p,_ in calls if p=='workspace/edit/apply'])==1
                gates[1].set();approval.wait_for(state='visible',timeout=10000)
                approval.get_by_role('button',name='رفض الخطوة',exact=True).click();approval.wait_for(state='hidden')
                assert len([p for p,_ in calls if p=='agent/execute'])==3,'Next unapproved tool must not run'
                assert not errors,errors
                if config.get('screenshotDir'):
                    destination=Path(config['screenshotDir']);destination.mkdir(parents=True,exist_ok=True)
                    page.screenshot(path=str(destination/'mission-board.png'))
                context.close();browser.close()
            return {'status':'passed','approved_project_plan':True,'popup_automatic':True,'dismiss_and_reopen_without_execution':True,
                'approval_closed_while_model_blocked':True,'tool_receipt_before_model':True,'double_click_executed_once':True,
                'separate_save_popup':True,'saved_before_next_model':True,'next_action_requires_fresh_approval':True,
                'workspace_editor_updated_after_chat_save':True,'approval_review_inside_workspace':True,
                'note':'Real local scaffold, preview, save and model routing; provider HTTP responses are controlled, no live inference or Windows claim.'}
        finally:
            for gate in gates:gate.set()
            httpx.AsyncClient=real_client;server.should_exit=True;thread.join(timeout=10)
            assert not thread.is_alive()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--browser-config',required=True);parser.add_argument('--output')
    args=parser.parse_args();result=run(json.loads(Path(args.browser_config).read_text()));text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:Path(args.output).write_text(text)
    print(text)
