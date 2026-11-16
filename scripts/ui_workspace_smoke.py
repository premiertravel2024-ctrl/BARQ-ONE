"""Real React/FastAPI editor: drafts, disk conflicts, exact navigation and save."""
import argparse,json,os,sys,tempfile,threading,time
from pathlib import Path


def run(config):
    from playwright.sync_api import sync_playwright,expect
    import uvicorn
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
    with tempfile.TemporaryDirectory(prefix='barq-workspace-ui-') as folder:
        temp=Path(folder);project=temp/'project';project.mkdir();other=temp/'other';other.mkdir()
        source=project/'app.py';source.write_text('value = 1\nprint(value)\n')
        (project/'broken.py').write_text('value = 1\ndef broken(:\n    pass\n')
        (other/'other.py').write_text('print("other")\n')
        (project/'nested').mkdir();(project/'nested'/'find_me.py').write_text('nested = True\n')
        os.environ['AI_ROUTER_DATA_DIR']=str(temp/'state')
        import api
        from desktop import free_port
        port=free_port();server=uvicorn.Server(uvicorn.Config(api.app,host='127.0.0.1',port=port,log_level='error'))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        try:
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            assert server.started
            errors=[]
            with sync_playwright() as runtime:
                browser=runtime.chromium.launch(headless=True,executable_path=config['executablePath'],args=config.get('args',[]))
                context=browser.new_context(viewport={'width':1440,'height':1000})
                state={'language':'ar','theme':'dark','workspace':str(project),'activeId':'workspace',
                    'chats':[{'id':'workspace','title':'اختبار المحرر','createdAt':1,'updatedAt':1,'messages':[]}]}
                context.add_init_script('localStorage.setItem("ai-router-premium-ui-v2",'+json.dumps(json.dumps({'state':state,'version':0}))+');')
                def route(request_route):
                    path=request_route.request.url.split('/v1/',1)[-1].split('?',1)[0]
                    if path.startswith(('studio/','workspace/','coding/')):request_route.continue_();return
                    fixtures={'router/models':{'models':[]},'router/providers':{'providers':[]},'conversations':{'conversations':[]},
                        'router/connectivity':{'mode':'auto','cloud_connection':'not_checked_or_restored','ollama':{'enabled':False,'reachable':False,'models':[]}},
                        'computer/status':{'supported':False,'status':'not_supported'}}
                    request_route.fulfill(status=200,content_type='application/json',body=json.dumps(fixtures.get(path,{})))
                context.route('**/v1/**',route)
                context.add_init_script('localStorage.setItem("barq-studio-recent","{}")')
                page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{port}',wait_until='networkidle')
                page.evaluate('window.dispatchEvent(new Event("barq-open-workspace"))')
                studio=page.get_by_role('region',name='مساحة برمجة برق')
                try:studio.get_by_role('treeitem',name='app.py',exact=True).click(timeout=10000)
                except Exception:
                    print(json.dumps({'errors':errors,'body':page.locator('body').inner_text()[:8000]},ensure_ascii=False),flush=True)
                    raise
                editor=studio.get_by_role('textbox',name='محرر الكود',exact=True)
                expect(editor).to_have_value('value = 1\nprint(value)\n')
                # Filter must find files even when their parent folder is collapsed.
                studio.get_by_role('treeitem',name='nested',exact=True).click()
                studio.get_by_role('textbox',name='فلترة الملفات',exact=True).fill('find_me')
                expect(studio.get_by_role('treeitem',name='find_me.py',exact=True)).to_be_visible()
                studio.get_by_role('textbox',name='فلترة الملفات',exact=True).fill('')
                editor.focus();editor.press('Control+Home');editor.press('ArrowDown')
                expect(studio.locator('.studio-status')).to_contain_text('Ln 2, Col 1')
                for width,height in [(1440,1000),(1000,760)]:
                    page.set_viewport_size({'width':width,'height':height})
                    page.wait_for_timeout(150)
                    bounds=studio.locator('.studio-editor').bounding_box()
                    assert bounds and bounds['width']>250,bounds
                    assert studio.evaluate('(el)=>el.scrollWidth <= el.clientWidth + 1')
                    if config.get('screenshotDir'):
                        destination=Path(config['screenshotDir']);destination.mkdir(parents=True,exist_ok=True)
                        page.screenshot(path=str(destination/f'studio-polish-{width}.png'))
                page.set_viewport_size({'width':1440,'height':1000})
                editor.fill('value = 9\nprint(value)\n')
                studio.get_by_role('button',name='الرجوع للمحادثة',exact=True).click()
                page.evaluate('window.dispatchEvent(new Event("barq-open-workspace"))')
                expect(editor).to_have_value('value = 9\nprint(value)\n')
                # An externally completed write must preserve the local dirty draft.
                source.write_text('value = 2\nprint(value)\n')
                page.evaluate('(workspace)=>window.dispatchEvent(new CustomEvent("barq-workspace-changed",{detail:{workspace}}))',str(project))
                expect(studio.get_by_role('alert')).to_contain_text('الملف اتغير على القرص')
                expect(editor).to_have_value('value = 9\nprint(value)\n')
                studio.get_by_role('button',name='احتفظ بمسودتي للمراجعة',exact=True).click()
                studio.get_by_role('button',name='معاينة الحفظ',exact=True).click()
                diff=studio.locator('.studio-diff-code');expect(diff).to_contain_text('-value = 2');expect(diff).to_contain_text('+value = 9')
                assert source.read_text()=='value = 2\nprint(value)\n'
                studio.get_by_role('button',name='الموافقة والحفظ',exact=True).click()
                expect(editor).to_have_value('value = 9\nprint(value)\n')
                assert source.read_text()=='value = 9\nprint(value)\n'
                studio.get_by_role('treeitem',name='broken.py',exact=True).click()
                expect(editor).to_have_value('value = 1\ndef broken(:\n    pass\n')
                editor.fill('local_unsaved = True\n')
                studio.get_by_role('button',name='المخرجات',exact=True).click()
                studio.get_by_role('button',name='تراجع عن آخر حفظ',exact=True).click()
                page.wait_for_function('document.body.innerText.includes("تم التراجع")')
                assert source.read_text()=='value = 2\nprint(value)\n'
                expect(editor).to_have_value('local_unsaved = True\n')
                studio.get_by_role('treeitem',name='app.py',exact=True).click()
                # Clean editor tracks disk, including new files in the explorer.
                source.write_text('value = 4\nprint(value)\n');(project/'new.py').write_text('print("new")\n')
                studio.get_by_role('button',name='تحديث الملفات من القرص',exact=True).click()
                expect(editor).to_have_value('value = 4\nprint(value)\n')
                expect(studio.get_by_role('treeitem',name='new.py',exact=True)).to_be_visible()
                # Declining a project change preserves the draft and selected root.
                editor.fill('value = 5\nprint(value)\n')
                studio.get_by_role('textbox',name='مسار المشروع',exact=True).fill(str(other))
                page.once('dialog',lambda dialog:dialog.dismiss())
                studio.get_by_role('button',name='فتح المشروع',exact=True).click()
                expect(editor).to_have_value('value = 5\nprint(value)\n')
                expect(studio.get_by_role('textbox',name='مسار المشروع',exact=True)).to_have_value(str(project))
                # Search navigates to the matching line, not just the file.
                studio.get_by_role('button',name='البحث',exact=True).click()
                studio.get_by_role('textbox',name='بحث بالكود',exact=True).fill('print(value)')
                studio.get_by_role('button',name='بحث',exact=True).click()
                studio.locator('.studio-search-result').filter(has_text='app.py:2').click()
                expect(editor).to_have_value('value = 5\nprint(value)\n')
                page.wait_for_function("document.querySelector('textarea[aria-label=\"محرر الكود\"]')?.selectionStart === 10")
                # Diagnostics opens the actual failing syntax location.
                studio.get_by_role('button',name='فحص',exact=True).click()
                studio.get_by_role('button',name='broken.py:2',exact=True).click()
                # Diagnostics never discard an unsaved buffer to jump to the disk issue.
                expect(editor).to_have_value('local_unsaved = True\n')
                assert not errors,errors
                context.close();browser.close()
            return {'status':'passed','malformed_recent_recovers':True,'collapsed_filter_visible':True,'keyboard_cursor_status':True,'responsive_layout':True,'draft_survives_chat':True,'external_change_keeps_draft':True,
                'review_uses_latest_disk':True,'approved_save_written':True,'clean_file_and_tree_refresh':True,
                'cancelled_project_switch_keeps_draft':True,'search_exact_line':True,'diagnostics_keeps_draft':True,'undo_preserves_other_draft':True,
                'note':'Actual browser and local file operations; no live model or Windows EXE test.'}
        finally:server.should_exit=True;thread.join(timeout=10);assert not thread.is_alive()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--browser-config',required=True);parser.add_argument('--output')
    args=parser.parse_args();result=run(json.loads(Path(args.browser_config).read_text()));text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:Path(args.output).write_text(text)
    print(text)
