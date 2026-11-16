"""Offline BARQ network smoke/benchmark: no external models or API keys used."""
import json,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from command_network.contracts import Request
from command_network.registry import Capability
from command_network.routing import DecisionRouter
from command_network.triage import Triage

DEMO_MODELS=[
 Capability(id='groq/fast-demo',provider='groq',name='fast-demo',kind='cloud',configured=True,context_window=16000,
    strengths={'chat':.9,'translation':.86,'qa':.82,'writing':.8},p50_latency=.25,reliability=.9,arabic_quality=.8),
 Capability(id='cloud/coder-demo',provider='cloud',name='coder-demo',configured=True,context_window=32000,
    strengths={'coding':.96,'debugging':.95,'reasoning':.94,'qa':.7,'tool':.88},p50_latency=1.1,reliability=.95,arabic_quality=.82,supports_tools=True),
 Capability(id='vision/vision-demo',provider='vision',name='vision-demo',configured=True,context_window=128000,
    modalities=['text','image'],strengths={'vision':.98,'long_document':.9,'summarization':.86,'qa':.8},p50_latency=2,reliability=.88,arabic_quality=.84),
 Capability(id='ollama/local-demo',provider='ollama',name='local-demo',kind='local',configured=True,context_window=8192,
    strengths={'qa':.7,'chat':.72,'coding':.6,'debugging':.55},p50_latency=1.7,reliability=.85,arabic_quality=.6),
]
CASES=[
 ('سؤال عربي','ليه السما زرقا؟',[]),
 ('إصلاح Python','فيه خطأ Traceback في Python main.py، صلحه',[ ]),
 ('تلخيص PDF طويل','لخص المستند الطويل report.pdf مع كل نقاطه المهمة',[]),
 ('سؤال عن صورة','اشرح اللي في الصورة دي',[{'type':'image/png','name':'photo.png'}]),
 ('مشروع متعدد الخطوات','نفذ التعديلات على البرنامج ثم شغل الاختبارات واراجع النتيجة',[]),
]
def run():
    triage=Triage();router=DecisionRouter(random_source=lambda:1.)
    results=[]
    for label,text,attachments in CASES:
        start=time.perf_counter();req=Request(messages=[{'role':'user','content':text}],attachments=attachments)
        profile=triage.classify(req);plan=router.plan(req,profile,DEMO_MODELS)
        results.append({'case':label,'classification':profile.task_type,'difficulty':profile.difficulty,
            'strategy':plan.strategy,'first_model':plan.chain[0] if plan.chain else None,
            'reason':plan.reason,'routing_overhead_ms':round((time.perf_counter()-start)*1000,2)})
    return results
if __name__=='__main__':
    output=run();print(json.dumps({'note':'Synthetic demo models only. No providers were contacted.','cases':output},ensure_ascii=False,indent=2))
