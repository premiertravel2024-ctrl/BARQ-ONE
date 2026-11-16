"""Real browser AudioWorklet/microphone lifecycle with a controlled Live WebSocket."""
import argparse,base64,json,threading
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from functools import partial
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

def run(config):
    root=Path(__file__).resolve().parents[1]
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(root/'web/react')))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=config['executablePath'],headless=True,args=config.get('args',[])+['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'])
            context=browser.new_context(viewport={'width':1280,'height':900},permissions=['microphone'])
            state={'language':'ar','theme':'dark','activeId':'voice-test','chats':[{'id':'voice-test','title':'مكالمة برق','createdAt':1,'updatedAt':1,'messages':[{'id':'intro','role':'user','content':'اسمي أشرف','createdAt':1}]}]}
            context.add_init_script('localStorage.setItem("ai-router-premium-ui-v2",'+json.dumps(json.dumps({'state':state,'version':0}))+');')
            context.add_init_script('''window.testStreams=[];window.testContexts=[];window.stoppedAudio=0;
const get=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);navigator.mediaDevices.getUserMedia=async(...args)=>{const stream=await get(...args);window.testStreams.push(stream);return stream;};
const AC=window.AudioContext;window.AudioContext=class extends AC{constructor(...args){super(...args);window.testContexts.push(this);}createBufferSource(){const node=super.createBufferSource();const stop=node.stop.bind(node);node.stop=(...args)=>{window.stoppedAudio++;return stop(...args);};return node;}};''')
            def route(r):
                path=r.request.url.split('/v1/',1)[-1].split('?')[0]
                data={'voice/settings':{'configured':True,'live_configured':True},'router/models':{'models':[]},'router/providers':{'providers':[]},'conversations':{'conversations':[]},'router/connectivity':{'mode':'auto','ollama':{'enabled':False,'reachable':False,'models':[]}}}.get(path,{})
                r.fulfill(status=200,content_type='application/json',body=json.dumps(data))
            context.route('**/v1/**',route)
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            sockets=[];packets=[];history=[]
            def socket_handler(ws):
                sockets.append(ws)
                def message(data):
                    if isinstance(data,bytes):packets.append(data)
                    else:history.append(json.loads(data))
                ws.on_message(message);ws.send(json.dumps({'type':'ready'}))
            page.route_web_socket('**/v1/voice/live*',socket_handler)
            page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='networkidle')
            page.get_by_role('button',name='مكالمة صوتية مباشرة مع برق',exact=True).click()
            dialog=page.get_by_role('dialog',name='مكالمة مع برق')
            dialog.get_by_role('button',name='ابدأ المكالمة',exact=True).click()
            expect(dialog.get_by_role('status')).to_contain_text('سامعك',timeout=15000)
            page.wait_for_timeout(300)
            assert packets and all(len(data)==2048 for data in packets)
            assert any(msg.get('type')=='context' and msg['messages'][0]['content']=='اسمي أشرف' for msg in history)
            ws=sockets[-1]
            for event in [{'type':'input_text','text':'صباح الخير'},{'type':'output_text','text':'صباح الفل يا أشرف'},{'type':'audio','data':base64.b64encode(b'\0\0'*24000*3).decode()}]:ws.send(json.dumps(event))
            expect(dialog).to_contain_text('صباح الفل يا أشرف')
            page.wait_for_timeout(100);ws.send(json.dumps({'type':'interrupt'}))
            page.wait_for_function('window.stoppedAudio>0')
            dialog.get_by_role('button',name='كتم الميكروفون',exact=True).click()
            assert page.evaluate('window.testStreams.every(s=>s.getAudioTracks().every(t=>!t.enabled))')
            dialog.get_by_role('button',name='تشغيل الميكروفون',exact=True).click()
            assert page.evaluate('window.testStreams.every(s=>s.getAudioTracks().every(t=>t.enabled))')
            dialog.get_by_role('button',name='إنهاء المكالمة',exact=True).click()
            page.wait_for_function('window.testStreams.every(s=>s.getTracks().every(t=>t.readyState==="ended"))&&window.testContexts.every(c=>c.state==="closed")')
            saved=page.evaluate('JSON.parse(localStorage.getItem("ai-router-premium-ui-v2")).state.chats[0].messages')
            assert any(m['content']=='صباح الخير' for m in saved)
            assert any(m['content']=='صباح الفل يا أشرف' for m in saved)
            if config.get('screenshotDir'):
                dest=Path(config['screenshotDir']);dest.mkdir(exist_ok=True,parents=True);page.screenshot(path=str(dest/'live-voice.png'))
            assert not errors,errors
            browser.close()
            return {'status':'passed','pcm16_worklet_packets':True,'context_sent':True,'interruption_stops_playback':True,'mute_resume':True,'microphone_and_contexts_closed':True,'transcripts_saved':True,'scope':'Synthetic microphone and controlled WebSocket; no real Gemini inference or acoustic/latency test'}
    finally:server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--browser-config',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    result=run(json.loads(Path(args.browser_config).read_text()));Path(args.output).write_text(json.dumps(result,indent=2));print(json.dumps(result))
