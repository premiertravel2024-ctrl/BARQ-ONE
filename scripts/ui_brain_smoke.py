"""Browser regression for collapsed branding and live reply rendering using local fixtures.

Run a local API first, then: python scripts/ui_brain_smoke.py --base-url http://127.0.0.1:8000
Requires Playwright and an installed browser; no live AI service is used.
"""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def run(base_url,config=None,screenshot_dir=None):
    config=config or {}
    captured=[]
    with sync_playwright() as runtime:
        launch={'headless':True}
        if config.get('executablePath'):launch.update(executable_path=config['executablePath'],args=config.get('args',[]))
        for language,width,theme in [('ar',1440,'dark'),('en',1440,'light'),('ar',390,'dark')]:
            browser=runtime.chromium.launch(**launch)
            context=browser.new_context(viewport={'width':width,'height':900},device_scale_factor=1)
            state={'theme':theme,'language':language,'sidebarCollapsed':True,'activeId':'ui-check',
                   'chats':[{'id':'ui-check','title':'تجربة برق','createdAt':1,'updatedAt':1,'pinned':False,'messages':[
                       {'id':'user','role':'user','content':'خفيف زي السهم؟','createdAt':1},
                       {'id':'reply','role':'assistant','content':'خفيف زي الريشة يا صاحبي. أنا برق ومعاك خطوة بخطوة.','createdAt':2}]}]}
            context.add_init_script('try{localStorage.setItem("ai-router-premium-ui-v2",'+json.dumps(json.dumps({'state':state,'version':0}))+');}catch{}')
            def api(route):
                path=route.request.url.split('/v1/',1)[-1].split('?',1)[0]
                if path in ('brain/route','router/chat/stream'):
                    route.continue_()  # Exercise the actual backend for the name-call regression.
                    return
                fixtures={'router/models':{'models':[]},'router/connectivity':{'mode':'auto','cloud_connection':'not_checked_or_restored','ollama':{'enabled':True,'reachable':False,'models':[],'message':'Test fixture'}},'router/providers':{'providers':[]},'conversations':{'conversations':[]},
                          'computer/status':{'supported':False,'status':'not_supported'},
                          'brain/state':{'task':{'id':'mission','goal':'فحص المشروع وتعديل الملف','status':'awaiting_approval',
                            'events':[{'kind':'tool','label':'workspace_read','success':True}],'saved_paths':[]}}}
                route.fulfill(status=200,content_type='application/json',body=json.dumps(fixtures.get(path,{})))
            context.route('**/v1/**',api)
            page=context.new_page();errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(base_url,wait_until='networkidle')
            if not page.locator('aside[aria-label=\"Sidebar\"]').count():
                if screenshot_dir:page.screenshot(path=str(screenshot_dir/'debug.png'))
                raise AssertionError({'errors':errors,'html':page.content()[:1200],'body':page.locator('body').inner_text()[:1200]})
            if width>=1024:
                rail=page.locator('aside[aria-label="Sidebar"]')
                header=rail.locator('.sidebar-brand-header')
                assert header.get_attribute('data-compact')=='true'
                assert rail.locator('.sidebar-brand-lockup').count()==0
                assert page.locator('main > header').bounding_box()['y']<8, 'The old mode strip must not consume a header row'
                button=header.locator('button')
                bounds=header.bounding_box();control=button.bounding_box()
                assert control['x']>=bounds['x'] and control['x']+control['width']<=bounds['x']+bounds['width']
                button.click();page.wait_for_timeout(500)
                lockup=rail.locator('.sidebar-brand-lockup');assert lockup.is_visible()
                bounds=rail.bounding_box();brand=lockup.bounding_box()
                assert brand['x']>=bounds['x'] and brand['x']+brand['width']<=bounds['x']+bounds['width']
                rail.locator('.sidebar-brand-header button').click();page.wait_for_timeout(500)
                assert rail.locator('.sidebar-brand-lockup').count()==0
                navigation=rail.locator('nav.sidebar-workspaces')
                navigation.get_by_role('button',name='مساحة العمل' if language=='ar' else 'Workspace',exact=True).click()
                workspace=page.locator('section.barq-studio[data-chat-mode="unified"]')
                workspace.wait_for(state='visible')
                assert workspace.locator('form').count()==0, 'Studio must not contain a second chat form'
                navigation.get_by_role('button',name='المحادثة' if language=='ar' else 'Chat',exact=True).click()
            else:
                page.get_by_role('button',name='فتح الشريط الجانبي',exact=True).click()
                page.wait_for_timeout(500)
                expanded=page.locator('.sidebar-brand-lockup:visible')
                assert expanded.count()==1 and expanded.bounding_box()['width']>60
                if screenshot_dir:
                    destination=screenshot_dir/'mobile-ar.png';page.screenshot(path=str(destination));captured.append(str(destination))
                drawer=page.locator('aside[aria-label="Mobile sidebar"]')
                drawer.locator('nav.sidebar-workspaces').get_by_role('button',name='مساحة العمل',exact=True).click()
                workspace=page.locator('section.barq-studio[data-chat-mode="unified"]')
                workspace.wait_for(state='visible')
                assert workspace.locator('form').count()==0, 'Studio must not contain a second chat form'
                # Studio has its own main-chat return control on mobile.
                workspace.get_by_role('button',name='الرجوع للمحادثة',exact=True).click()
                page.locator('#chatComposer').wait_for(state='visible')
            page.locator('#chatComposer').fill('برق')
            page.locator('#chatComposer').press('Enter')
            page.wait_for_function("document.querySelectorAll('.chat-markdown').length>0 && [...document.querySelectorAll('.chat-markdown')].at(-1).textContent.includes('أيوه، معاك. قولّي.')")
            assert page.locator('.chat-markdown').last.inner_text()=='أيوه، معاك. قولّي.'
            page.wait_for_timeout(300)  # Allow the message entrance animation to settle before capture.
            if screenshot_dir and width>=1024:
                destination=screenshot_dir/f'collapsed-{language}-{theme}.png';page.screenshot(path=str(destination));captured.append(str(destination))
            assert page.locator('section[aria-label="متابعة مهمة برق"], section[aria-label="BARQ task progress"]').count()==1
            assert not errors,errors
            context.close()
            browser.close()
    return {'status':'passed','cases':3,'screenshots':captured}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    parser.add_argument('--browser-config')
    parser.add_argument('--screenshot-dir')
    args=parser.parse_args()
    directory=Path(args.screenshot_dir) if args.screenshot_dir else None
    if directory:directory.mkdir(parents=True,exist_ok=True)
    config=json.loads(Path(args.browser_config).read_text()) if args.browser_config else None
    print(json.dumps(run(args.base_url,config,directory),ensure_ascii=False))
