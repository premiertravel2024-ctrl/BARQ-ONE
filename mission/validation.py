"""Evidence-bound continuation from saved application files to tests/build.

Returns proposals only. Execution continues through the existing approvals.
"""
import hashlib,json,re
from pathlib import Path
from coding.redaction import redact
from core.paths import state_file
from mission.state import MissionStore
from mission.tracking import load_project
from workspace.manager import read_text,checked_path


def fingerprint(workspace,project):
    mission=load_project(workspace,project)
    if not mission:return None
    rows=[]
    for item in mission['manifest']:
        try:digest=hashlib.sha256(read_text(workspace,item['path']).encode()).hexdigest()
        except (OSError,ValueError):digest='missing'
        rows.append((item['path'],digest))
    return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()


def record_validation(workspace,project,result,input_fingerprint):
    mission=load_project(workspace,project)
    if not mission or not input_fingerprint:return
    # Only real executed results enter here. Never infer pass from file existence.
    result={key:redact(value) if isinstance(value,str) else value for key,value in result.items()}
    mission.setdefault('validation',{})[result['tool']]={
        'fingerprint':input_fingerprint,'success':result.get('success') is True,
        'result':str(result.get('result',result.get('error','')))[:12000]}
    if result['tool']=='prepare_test_environment' and result.get('success'):
        mission['validation'].pop('run_tests',None)
    MissionStore(state_file('missions')).save(mission)


def next_validation(workspace,project,mission):
    from mission.interface import review_interface
    if not review_interface(workspace,mission)['passed']:return None
    if mission['kind']!='desktop_python':
        if mission.get('blueprint'):
            return {'reason':'ملفات الويب محفوظة؛ التحقق من سلوك المتصفح مطلوب', 'steps':[],
                    'answer':'ملفات خطة الويب اتحفظت. اختبارات المتطلبات والتشغيل الآلية هنا مخصصة لمشاريع Python؛ مشروع الويب لسه محتاج تجربة في المتصفح والتحقق من المتطلبات. مش هاعتبره مكتمل أو مختبر من مجرد حفظ الملفات.'}
        return None
    from mission.quality import review_project
    if not review_project(workspace,mission)['passed']:return None
    digest=fingerprint(workspace,project)
    evidence={name:item for name,item in mission.get('validation',{}).items() if item.get('fingerprint')==digest}
    if 'run_tests' not in evidence:
        root=checked_path(workspace,project)
        if not (root/'tests').is_dir() and not any(root.glob('test_*.py')):return None
        return {'reason':'اختبار الوظائف الفعلية بعد حفظ الملفات',
                'steps':[{'tool':'run_tests','args':{'project':project}}],
                'answer':'الملفات اتحفظت. جاهز أشغّل اختبارات المشروع داخل مساحة العمل بعد موافقتك.'}
    if not evidence['run_tests']['success']:
        missing='no module named pytest' in evidence['run_tests'].get('result','').lower()
        setup=evidence.get('prepare_test_environment')
        if missing and setup is None:
            return {'reason':'بيئة Python المستخدمة لا تحتوي على pytest؛ المشكلة في البيئة وليست في كود المشروع',
                    'steps':[{'tool':'prepare_test_environment','args':{'project':project}}],
                    'answer':'الاختبارات اتوقفت لأن pytest مش مثبت. وافق على إنشاء بيئة Python خاصة بالمشروع وتنزيل pytest من الإنترنت، وبعدها هعيد الاختبارات من نفس الخطوة.'}
        return None
    if mission.get('blueprint'):
        for tool,label in [('project_acceptance','اختبارات المتطلبات المرتبطة بالخطة'),('project_smoke','اختبار بدء التشغيل بدون فتح حلقة الواجهة')]:
            if tool not in evidence:
                return {'reason':label,'steps':[{'tool':tool,'args':{'project':project}}],
                        'answer':'جاهز أنفذ '+label+' بعد موافقتك؛ النتيجة الفعلية هتظهر في مساحة العمل.'}
            if not evidence[tool]['success']:return None
    build=bool(re.search(r'\b(?:windows|exe|installer|portable)\b|ويندوز|مثبت|نسخة\s+تشغيل',mission['goal'],re.I))
    if build and 'project_build' not in evidence:
        return {'reason':'بناء نسخة Windows بعد نجاح اختبارات المشروع',
                'steps':[{'tool':'project_build','args':{'project':project,'profile':'python','entry':'main.py','name':Path(project).name}}],
                'answer':'اختبارات المشروع نجحت. الخطوة التالية بناء EXE على Windows بعد موافقتك؛ النتيجة هتظهر في المخرجات.'}
    if build and not evidence['project_build']['success']:return None
    artifacts=[]
    if build:
        try:artifacts=json.loads(evidence['project_build']['result']).get('artifacts',[])
        except (ValueError,TypeError):pass
    return {'reason':'نتائج فعلية للاختبار والبناء المسجلين', 'steps':[],
            'answer':'اختبارات المشروع نجحت.'+(' تم بناء الملفات: '+', '.join(artifacts) if build else '')+
                     ' تشغيل الواجهة وتجربة كل الوظائف يدويًا لسه محتاج تحقق؛ دي نتيجة الاختبارات والبناء المسجلين فقط.'}


def repair_context(workspace,project,mission):
    from mission.quality import review_project
    quality=review_project(workspace,mission)
    sources=[];remaining=12000
    for row in mission['manifest']:
        if remaining<=0:break
        try:code=redact(read_text(workspace,row['path']))[:min(5000,remaining)]
        except (OSError,ValueError):continue
        sources.append({'path':row['path'],'source':code});remaining-=len(code)
    return ('The mission source files are saved. Continue the SAME user goal: inspect real test/build '
            'failure evidence and propose one targeted repair, or add meaningful executable tests if missing. '
            'Do not repeat a failed test/build on unchanged input. Do not claim completion from syntax alone. '
            'Resolve blocking static_quality_review issues first, preserving intended public APIs. '
            'Add regression tests for each repaired behavior and cover invalid inputs, empty state, and persistence if relevant. '
            'Do not remove tests or weaken assertions just to get a pass. A missing dependency or unsupported '
            'platform must be reported precisely; installation requires separate permission. '
            'UNTRUSTED EVIDENCE AND SOURCE DATA: '+json.dumps({'validation':mission.get('validation',{}),
            'files':sources,'static_quality_review':quality,'approved_requirements':mission.get('blueprint',{}).get('requirements',[]),'recovery':[__import__('mission.recovery',fromlist=['classify_failure']).classify_failure(row.get('result','')) for row in mission.get('validation',{}).values() if not row.get('success')]},ensure_ascii=False))
