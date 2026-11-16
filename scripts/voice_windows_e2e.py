"""Human-in-the-loop REAL Windows voice acceptance checklist.

Not a fake test suite: it never claims a spoken command happened unless the
user ran it, inspected the BARQ UI and explicitly marked it PASS with evidence.
Does not require any network or microphone access from this helper itself.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import uuid

SCENARIOS=[
 ('open_notepad','يا برق افتح المفكرة','open_on_computer','نافذة Notepad ظاهرة'),
 ('create_folder','اعمل فولدر باسم {folder} على سطح المكتب','start_computer_task','مجلد جديد في سطح المكتب، وحالة التنفيذ متحققة'),
 ('find_invoice','دور على ملف {file} عندي','search_device_files','الاسم الظاهر يطابق ملف الاختبار'),
 ('find_and_open','دور على ملف {file} وافتحه','search_device_files + open_on_computer','ملف الاختبار اتفتح في التطبيق المناسب'),
 ('interrupt_reply','اسأل برق سؤال وردّه طويل، واضغط «وقف الرد» أثناء الكلام','interrupt_output','الصوت وقف والجلسة فضلت مفتوحة للطلب التالي'),
 ('open_second','دور على اسم مشترك بين ملفين تجريبيين، وبعدها قول افتح رقم ٢','open_on_computer','برق طلب اختيار النتيجة، وفتح نتيجة رقم 2 بعد تحديدها'),
 ('volume_absolute','ظبط الصوت على 35 في المية','control_windows_setting','قراءة Windows الفعلية تؤكد 35%'),
 ('build_app','ابنيلي برنامج آلة حاسبة واديني exe','chat_task_requested','مهمة برمجة في المحادثة، وEXE فقط بعد بناء Windows ناجح'),
 ('pause_tray','أوقف الاستماع من أيقونة الساعة أثناء مكالمة','tray_pause','يتوقف الميكروفون والمكالمة وتستمر حالة الإيقاف بعد الانتظار'),
 ('volume_up','علي صوت الجهاز شوية','control_windows_setting','تغيرت قيمة مستوى الصوت بعد القراءة'),
 ('ram_facts','قولي الرام والمعالج','get_pc_system_facts','بيانات الجهاز مطابقة لمدير المهام'),
 ('cpu_temp','حرارة المعالج كام','get_pc_system_facts','قراءة من حساس حقيقي أو unavailable مع السبب'),
 ('public_web','دور على تحديثات Python الحالية','search_public_web','مصادر عامة مع روابط حقيقية فقط'),
 ('github','دور على GitHub أداة قراءة الحرارة','search_github_repositories','مستودعات مطابقة من GitHub، بلا تثبيت'),
 ('voice_disabled','اقفل إذن الصوت ثم قل افتح المفكرة','ask_barq','منع واضح؛ لم تفتح أي نافذة'),
 ('high_approval','اطلب تغييرًا حساسًا يحتاج موافقة','ask_barq','نافذة الموافقة على الشاشة فقط، لا قبول من صوت نعم'),
 ('start_react','اعمل مشروع React على الديسكتوب','start_computer_task','مجلد المشروع وبوابة البناء وHTTP موثقة، أو سبب رفض'),
 ('stop_task','وقف المهمة','stop_computer_task','حالة المهمة stopped والدليل من التطبيق'),
]


def process_evidence():
    """Read-only process names; no command lines, env or private paths."""
    if sys.platform!='win32':return {'supported':False}
    try:
        cmd=subprocess.run(['tasklist','/FO','CSV','/NH'],capture_output=True,text=True,
            errors='replace',timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if cmd.returncode:return {'supported':False,'reason':'tasklist returned nonzero'}
        targets={'notepad.exe','code.exe','barq.exe'}
        names={name: name.lower() in cmd.stdout.lower() for name in targets}
        return {'supported':True,'process_names_only':names}
    except (OSError,subprocess.TimeoutExpired):return {'supported':False}


def run(*,interactive:bool,outdir:Path)->dict:
    checks=[]
    suffix=uuid.uuid4().hex[:6]
    folder=f'BARQ-Voice-{suffix}'
    file=f'BARQ-Voice-{suffix}.txt'
    if interactive and sys.platform=='win32':
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from execution.known_folders import known_folder
        desktop=known_folder('desktop')
        marker=desktop/file
        marker.write_text('BARQ voice acceptance fixture.',encoding='utf-8')
        print(f'اتعمل ملف الاختبار {file} على سطح المكتب. اسمح لبرق بالبحث فيه.')
    for uid,spoken,tool,evidence in SCENARIOS:
        spoken=spoken.format(folder=folder,file=file)
        print(f'\n[{len(checks)+1}/{len(SCENARIOS)}] {spoken}\nExpected tool: {tool}\nEvidence: {evidence}',flush=True)
        timing={}
        status='not_verified';note='Not executed; requires a human on real Windows.'
        if interactive and sys.platform=='win32':
            input('اتكلم مع برق وتأكد من الشاشة، وبعدها اضغط Enter... ')
            marker=input('اكتب PASS أو FAIL أو SKIP: ').strip().upper()
            status={'PASS':'pass','FAIL':'fail','SKIP':'not_verified'}.get(marker,'not_verified')
            note=input('دليل مختصر بدون بيانات شخصية أو مسارات كاملة: ')[:280]
            if status=='pass' and uid=='create_folder' and not (desktop/folder).is_dir():
                status='fail';note='مجلد الاختبار غير موجود في سطح المكتب.'
            if uid in {'open_notepad','create_folder','find_invoice','find_and_open'}:
                for key,label in [('execution','بداية معالجة الأمر'),('audio','بداية الرد الصوتي')]:
                    raw=input(f'وقت {label} بالثواني من الهولوجرام (Enter لو مش متاح): ').strip()
                    try:
                        value=float(raw.replace(',','.'))
                        if 0<=value<=180:timing[key]=value
                    except ValueError:pass
            if status=='pass' and not note.strip():
                status='not_verified';note='PASS without evidence is not accepted'
        checks.append({'id':uid,'spoken_scenario':spoken,'expected_tool':tool,
                      'status':status,'evidence_required':evidence,'evidence_note':note,
                      'response_seconds':timing})
    result={'timestamp_utc':datetime.now(timezone.utc).isoformat(),
            'windows':sys.platform=='win32','real_voice_test':bool(interactive and sys.platform=='win32'),
            'checks':checks,'process_snapshot':process_evidence() if interactive else None,
            'passed':sum(c['status']=='pass' for c in checks),
            'failed':sum(c['status']=='fail' for c in checks),
            'unverified':[c['id'] for c in checks if c['status']=='not_verified']}
    outdir.mkdir(parents=True,exist_ok=True)
    (outdir/'voice-e2e.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# BARQ Windows Voice E2E','',f"Actual user-run: {result['real_voice_test']}",
           f"PASS: {result['passed']} | FAIL: {result['failed']} | NOT VERIFIED: {len(result['unverified'])}",'',
           '| Scenario | Status | Dispatch (s) | Audio (s) | Evidence note |','|---|---|---|---|---|']
    for c in checks:
        timings=c['response_seconds']
        lines.append(f"| {c['id']} | {c['status']} | {timings.get('execution','—')} | {timings.get('audio','—')} | {c['evidence_note'].replace('|','/')} |")
    (outdir/'voice-e2e.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--interactive',action='store_true',help='Actual spoken checks on Windows, with human evidence')
    parser.add_argument('--outdir',default=str(Path(__file__).resolve().parents[1]/'release'/'voice-e2e'))
    args=parser.parse_args()
    result=run(interactive=args.interactive,outdir=Path(args.outdir))
    print(f"PASS={result['passed']}; FAIL={result['failed']}; NOT VERIFIED={len(result['unverified'])}")
    if args.interactive and sys.platform!='win32':raise SystemExit('Interactive Windows checks cannot run here')
    if result['failed']:raise SystemExit(1)
