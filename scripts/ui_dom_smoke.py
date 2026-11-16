"""Browser DOM regression suite for the legacy UI without network/npm.

This test uses the application's *actual* HTML/CSS/JS, with only API responses
replaced by fixtures. It does not claim live-provider or Windows testing.
"""
from pathlib import Path
import base64
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
WEB=ROOT/'web'

def offline_html():
    doc=BeautifulSoup((WEB/'index.html').read_text(encoding='utf-8'),'html.parser')
    for tag in doc.select('link[href="/fonts/ui-refine.css"]'):
        style=doc.new_tag('style')
        style.string=(WEB/'fonts'/'ui-refine.css').read_text(encoding='utf-8')
        tag.replace_with(style)
    for tag in doc.select('script[src]'):
        name=tag['src'].split('/')[-1]
        tag.attrs.pop('src')
        tag.string=(WEB/'fonts'/name).read_text(encoding='utf-8')
    for image in doc.select('img[src^="/brand/"]'):
        local=WEB/image['src'].lstrip('/')
        if local.is_file():
            image['src']='data:image/png;base64,'+base64.b64encode(local.read_bytes()).decode('ascii')
    # Proprietary font is optional in source distributions; CSS falls back to Tahoma.
    font_file=WEB/'fonts/ge-ss-two-medium.otf'
    if font_file.is_file():
        font=font_file.read_bytes()
        embedded='data:font/otf;base64,'+base64.b64encode(font).decode('ascii')
        original=doc.select_one('style')
        original.string=original.get_text().replace('/fonts/ge-ss-two-medium.otf',embedded)
    return str(doc)

MOCK_SETUP=r"""() => {
 const store={};
 Object.defineProperty(window,'localStorage',{configurable:true,value:{
   getItem:k=>store[k]??null,setItem:(k,v)=>{store[k]=String(v)},removeItem:k=>delete store[k]
 }});
 const data={
  '/v1/models':{data:[{id:'gemini/gemini-2.5-flash'},{id:'ollama/qwen2.5-coder'}]},
  '/v1/router/models':{models:[{id:'gemini/gemini-2.5-flash',strengths:['fast'],available:true,configured:true,remaining_today:100},{id:'ollama/qwen2.5-coder',strengths:['code'],available:true,configured:true,remaining_today:999}]},
  '/v1/router/providers':{providers:[{name:'gemini',enabled:true,configured:true,remaining_today:100,models:['gemini-2.5-flash'],kind:'cloud',priority:1},{name:'ollama',enabled:true,configured:true,remaining_today:999,models:['qwen2.5-coder'],kind:'local',priority:5}]},
  '/v1/tools':{tools:[]},
  '/v1/voice/settings':{configured:false},
  '/v1/mcp/servers':{servers:[{id:'rea',enabled:false,installed:false}]},
  '/v1/router/connectivity':{mode:'auto',ollama:{enabled:true,reachable:true,models:['qwen2.5-coder']},cloud_connection:'online'},
  '/v1/conversations':{conversations:[]},
  '/v1/router/chat':{content:'إجابة تجريبية من نموذج البرمجة',model:'ollama/qwen2.5-coder',attempts:['gemini/gemini-2.5-flash: rate limit']},
  '/v1/agent/plan':{plan_id:'mock-plan-123',model:'ollama/qwen2.5-coder',plan:{reason:'فحص المشروع',steps:[{tool:'python_tests',args:{}}],answer:'جاهزة'}}
 };
 window.fetch=async(url,opts)=>{
   const path=String(url).split('?')[0];
   if(path==='/v1/router/chat/stream'){
     const encoder=new TextEncoder();
     const events=[
       ['routing',{status:'Routing to Ollama'}],
       ['model',{model:'ollama/qwen2.5-coder',provider:'ollama',attempts:['gemini/gemini-2.5-flash: rate limit'],offline:true}],
       ['token',{content:'إجابة تجريبية من نموذج البرمجة'}],
       ['metrics',{time_to_first_token_seconds:.12,characters_per_second:140,latency_seconds:.5,output_characters:35}],
       ['done',{finish_reason:'stop'}]
     ];
     return {ok:true,status:200,body:new ReadableStream({start(controller){
       for(const [type,detail] of events)controller.enqueue(encoder.encode(`event: ${type}\ndata: ${JSON.stringify(detail)}\n\n`));
       controller.close();
     }})};
   }
   return {ok:true,json:async()=>data[path]||{},status:200};
 };
}"""

def embed_runtime_images(page):
    # The smoke suite runs on about:blank with no HTTP server. Serve the exact
    # branded bytes for IMG elements created dynamically by the original JS.
    mapping={f'/brand/{file.name}':'data:image/png;base64,'+base64.b64encode(file.read_bytes()).decode('ascii')
             for file in (WEB/'brand').glob('*.png')}
    page.locator('img[src^="/brand/"]').evaluate_all('(items,images)=>items.forEach(img=>{if(images[img.getAttribute("src")])img.src=images[img.getAttribute("src")];})', mapping)

def check(page, condition, desc):
    if not condition:raise AssertionError(desc)
    print('PASS',desc)

def main():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage','--disable-gpu'])
        page=browser.new_page(viewport={'width':1440,'height':900})
        errors=[]
        page.on('pageerror',lambda err:errors.append(str(err)))
        page.evaluate(MOCK_SETUP)
        page.set_content(offline_html(),wait_until='domcontentloaded')
        page.wait_for_timeout(350)
        embed_runtime_images(page)
        check(page,page.locator('.sidebar .manager').count()==0,'No workspace tools in chat sidebar')
        check(page,page.locator('#settingsModal').is_hidden(),'Settings hidden by default')
        check(page,page.locator('#agentPlanCard').is_hidden(),'Plan hidden until approval is needed')
        check(page,page.locator('#send').is_disabled(),'Send disabled when composer empty')
        check(page,page.locator('.suggestion-card').count()==4,'Four suggestion cards')
        check(page,page.locator('.history-item').count()==1,'Single initial empty chat')
        page.screenshot(path=str(ROOT.parent/'BARQ_Actual_Empty.png'))
        page.locator('#new').click()
        check(page,page.locator('.history-item').count()==1,'New chat does not duplicate empty chat')
        page.locator('#topSettings').click()
        check(page,page.locator('#settingsModal').is_visible(),'Settings opens')
        page.locator('#tab-settingsPanelMcp').click()
        page.locator('#settingsPanelMcp details').evaluate_all('(nodes)=>nodes.forEach(n=>n.open=true)')
        check(page,page.locator('#reaEnable').is_visible() and page.locator('#gitAction').is_visible(),'REA and GitHub tools retained')
        page.screenshot(path=str(ROOT.parent/'BARQ_Actual_Settings.png'))
        page.locator('#tab-settingsPanelBuild').click()
        page.locator('#settingsPanelBuild details').evaluate_all('(nodes)=>nodes.forEach(n=>n.open=true)')
        check(page,page.locator('#buildPreview').is_visible(),'EXE builder retained')
        page.keyboard.press('Escape')
        check(page,page.locator('#settingsModal').is_hidden(),'Escape closes modal')
        page.locator('#modelTrigger').click()
        check(page,page.locator('.model-option').count()==3,'Searchable selector includes Auto and providers')
        page.locator('#modelSearch').fill('qwen')
        check(page,page.locator('.model-option').count()==1,'Model filtering works')
        page.keyboard.press('ArrowDown')
        page.keyboard.press('Enter')
        check(page,page.locator('#model').input_value()=='ollama/qwen2.5-coder','Keyboard model selection updates real form value')
        page.locator('.suggestion-card').first.click()
        check(page,page.locator('#send').is_enabled(),'Suggestion activates Send')
        page.locator('#prompt').fill('عايز كود Python نظيف')
        page.locator('#send').click()
        page.wait_for_timeout(300)
        check(page,page.locator('.bubble.user').count()==1 and page.locator('.bubble.assistant').count()==1,'Chat works with existing handler')
        check(page,page.locator('.fallback-note').count()==0,'Fallback telemetry hidden from chat')
        check(page,page.locator('.meta-badge').count()==0,'Model badge hidden in regular replies')
        check(page,page.locator('#chatTitle').inner_text().startswith('عايز كود'),'Chat named from first prompt')
        page.locator('#chatMore').click()
        page.locator('#deleteChat').click()
        check(page,page.locator('#confirmModal').is_visible() and 'عايز كود' in page.locator('#confirmMessage').inner_text(),'Delete dialog names chat')
        page.locator('#cancelDelete').click()
        check(page,page.locator('.history-item').count()==1,'Cancel delete does not remove chat')
        page.locator('#new').click()
        check(page,page.locator('.history-item').count()==2,'New chat created after conversation')
        page.locator('#topSettings').click();page.locator('#tab-settingsPanelTools').click();page.locator('#settingsPanelTools details').first.evaluate('(el)=>el.open=true');page.locator('#workspace').fill('C:/SampleProject');page.locator('#tab-settingsPanelAgent').click();page.locator('#agentEnabled').check();page.locator('#closeSettings').click()
        page.locator('#prompt').fill('اختبر المشروع');page.locator('#send').click();page.wait_for_timeout(200)
        check(page,page.locator('#agentPlanCard').is_visible(),'Pending plan card appears in chat flow')
        check(page,page.locator('#agentSteps li').count()==2,'Actual tool plan steps appear as a list')
        check(page,page.locator('#agentApprove').is_enabled(),'Plan approval button available')
        page.locator('#agentDiscard').click()
        check(page,page.locator('#agentPlanCard').is_hidden(),'Cancel plan hides card')
        check(page,page.locator('#settingsModal').is_hidden(),'Settings remains closed')
        page.locator('#topSettings').click();page.locator('#tab-settingsPanelModels').click()
        page.locator('#settingsPanelModels details').last.evaluate('(el)=>el.open=true')
        page.locator('#apiKeyInput').fill('TEST-NOT-REAL-KEY')
        page.locator('#saveApiKey').click()
        page.wait_for_timeout(30)
        check(page,page.locator('#saveApiKey').evaluate('(el)=>el.classList.contains("is-success")'),'Success state shown only after save call resolves')
        page.wait_for_timeout(1600)
        check(page,page.locator('#saveApiKey').inner_text().startswith('حفظ'),'Save label restored without layout shift')
        page.locator('#closeSettings').click()
        embed_runtime_images(page)
        page.screenshot(path=str(ROOT.parent/'BARQ_Actual_Chat.png'))
        check(page,len(errors)==0,'No uncaught browser JavaScript errors: '+str(errors))
        # Check responsive drawer on a real narrow viewport.
        mobile=browser.new_page(viewport={'width':390,'height':844})
        mobile_errors=[];mobile.on('pageerror',lambda err:mobile_errors.append(str(err)))
        mobile.evaluate(MOCK_SETUP);mobile.set_content(offline_html(),wait_until='domcontentloaded')
        mobile.locator('#sidebarToggle').click()
        check(mobile,mobile.locator('.sidebar').evaluate('(el)=>el.classList.contains("mobile-open")'),'Mobile sidebar opens as drawer')
        mobile.locator('#sidebarBackdrop').click(position={'x':15,'y':150})
        check(mobile,mobile.locator('.sidebar').evaluate('(el)=>!el.classList.contains("mobile-open")'),'Mobile sidebar closes with backdrop')
        check(mobile,len(mobile_errors)==0,'No mobile JavaScript errors: '+str(mobile_errors))
        mobile.close();browser.close()

if __name__=='__main__':main()
