"""On-device, read-only Windows facts for questions explicitly asking about this PC.

No shell, registry writes, environment dumps, browser history or credential reads.
Computer interaction is opt-in; the provider receives only the final short answer.
"""
from __future__ import annotations
import os
import platform
import re
import sys
from pathlib import Path


def _is_enabled() -> bool:
    try:
        from computer_control.api import load_policy
        return bool(load_policy().enabled)
    except (ImportError, OSError, ValueError, RuntimeError):
        return False


def snapshot() -> dict:
    """Bounded public device metadata, not personal documents or telemetry upload."""
    data = {
        'operating_system': platform.system(),
        'windows_version': platform.release(),
        'architecture': platform.machine(),
        'cpu': platform.processor() or 'غير متاح',
        'logical_cpu_count': os.cpu_count(),
    }
    try:
        import psutil
        m=psutil.virtual_memory()
        data['ram_gb']=round(m.total / (1024 ** 3), 1)
        data['ram_available_gb']=round(m.available / (1024 ** 3), 1)
        drives=[]
        for part in psutil.disk_partitions(all=False):
            if len(drives)>=12:break
            try:
                usage=psutil.disk_usage(part.mountpoint)
            except (OSError, PermissionError):
                continue
            # Only drive letter / mountpoint and capacity; no directory contents.
            drives.append({'drive':part.mountpoint,'total_gb':round(usage.total/(1024**3),1),
                           'free_gb':round(usage.free/(1024**3),1)})
        data['drives']=drives
        try:
            b=psutil.sensors_battery()
            if b is not None:
                data['battery_percent']=round(b.percent)
                data['charging']=bool(b.power_plugged)
        except (OSError, AttributeError, NotImplementedError):pass
        # Only names of active programs; never command lines, usernames or process paths.
        names=set()
        for proc in psutil.process_iter(['name']):
            try:
                name=str(proc.info.get('name') or '').strip()
                if name and not name.lower().startswith(('system','registry','smss.exe','lsass.exe')):
                    names.add(name)
            except (OSError, psutil.Error):continue
            if len(names)>=600:break
        data['process_names']=sorted(names,key=str.lower)[:150]
    except ImportError:
        data['telemetry_unavailable']='psutil is not installed'
    except (OSError, PermissionError):
        data['telemetry_unavailable']='Windows denied system metrics'
    return data


_THERMAL=re.compile(r'حرار|سخون|سخن|temperature|\btemp\b|تبريد')
_HARDWARE=re.compile(r'المعالج|بروسيسور|معالجي|\b(?:cpu|processor|gpu|rtx|ssd|nvme)\b|'
                     r'كار[تط] الشاش[هة]|كرت الشاش[هة]|الجرافيك|الهارد|الديسك|القرص|الجهاز|الكمبيوتر|اللابتوب|حاسوب')


def is_temperature_request(question: str) -> bool:
    """Recognize a single real-device measurement before either model router."""
    from voice.intent import command_text, is_multi_step, non_executable
    if len(question)>240 or any(c in question for c in '\r\n\x00') or non_executable(question):
        return False
    value=command_text(question)
    if is_multi_step(value) or _IMPERATIVE.search(value):
        return False
    return bool(_THERMAL.search(value) and _HARDWARE.search(value))


def _answer_sensor_question(question: str) -> str | None:
    """Specific hardware facts win over generic CPU/RAM model-name matches."""
    q = question.lower().replace('أ','ا').replace('إ','ا').replace('آ','ا')
    thermal = any(term in q for term in ('حرار','سخون','سخن','temperature','temp','تبريد'))
    workload = any(term in q for term in ('استهلاك','ضغط','استخدام','تحميل','load','usage'))
    target_cpu = any(term in q for term in ('المعالج','بروسيسور','البروسيسور','cpu','معالجي','processor'))
    target_gpu = any(term in q for term in ('كارت الشاشة','كرت الشاشة','كارت الشاشه','كرت الشاشه','gpu','الجرافيك','rtx'))
    target_disk = any(term in q for term in ('الهارد','ssd','nvme','الديسك','القرص'))
    target_pc = any(term in q for term in ('الجهاز','الكمبيوتر','اللابتوب','حاسوب'))
    if not (thermal or workload) or not (target_cpu or target_gpu or target_disk or target_pc):
        return None
    if thermal:
        from core.hardware_sensors import ensure_sensors_ready, snapshot as sensors_snapshot
        key='gpu_c' if target_gpu and not target_cpu else 'storage_c' if target_disk and not target_cpu else 'cpu_c'
        readings=sensors_snapshot(include_gpu=key=='gpu_c')
        reason=readings.get('reason')
        if readings.get(key) is None and reason=='monitor_not_installed':
            status=ensure_sensors_ready()
            if status=='installed':
                readings=sensors_snapshot(include_gpu=key=='gpu_c')
                reason=readings.get('reason')
            elif status=='timeout':
                return 'تجهيز الحساسات أخد وقت أطول من المهلة. مفيش قراءة مؤكدة لسه، وتفاصيل التجهيز موجودة في سجل الحساسات.'
            else:
                return 'تعذّر تجهيز الحساسات تلقائيًا. تأكد إن الإنترنت شغّال لو الأداة مش موجودة، وراجع sensor-install.log من مجلد بيانات برق. مفيش قراءة مؤكدة.'
        temp=readings.get(key)
        if key=='gpu_c':
            return (f'حرارة كارت الشاشة حاليًا {temp} درجة مئوية، حسب {readings.get("gpu_source") or readings.get("provider") or "مستشعر الجهاز"}.'
                    if temp is not None else 'مش لاقي قراءة موثوقة لحرارة كارت الشاشة من الحساسات حاليًا.')
        if key=='storage_c':
            return f'حرارة وحدة التخزين حوالي {temp} درجة مئوية حسب الحساس المحلي.' if temp is not None else 'حرارة وحدة التخزين مش متاحة من الحساسات حاليًا.'
        if temp is not None:
            return f'درجة حرارة المعالج حاليًا {temp} درجة مئوية، حسب {readings.get("cpu_sensor") or "حساس المعالج"} من LibreHardwareMonitor.'
        if reason == 'sensor_provider_unavailable':
            return ('LibreHardwareMonitor موجود، وبرق حاول يشغّله تلقائيًا، '
                    'بس قناة القراءة مش متاحة حتى بعد محاولة التشغيل. لو Windows '
                    'طلب صلاحية مسؤول، الموافقة عليها قرارك؛ مش هتتجاوز تلقائيًا. '
                    'مش هخمن درجة حرارة المعالج.')
        if reason == 'no_matching_sensors':
            return ('LibreHardwareMonitor شغال، لكن حساس حرارة CPU نفسه مش ظاهر. '
                    'اتأكد إن قراءة المعالج مفعّلة وإن البرنامج عنده الصلاحيات اللازمة. '
                    'مش هستخدم حرارة اللوحة الأم بدل حرارة CPU.')
        return ('مش قادر أقرأ حرارة المعالج حاليًا من حساسات موثوقة. '
                'جرب إصلاح الحساسات من مجلد برق، ومش هخمن الرقم.')
    if workload:
        try:
            import psutil
        except ImportError:
            return 'مكتبة قراءة استخدام المعالج والرام مش متاحة داخل برق حاليًا.'
        if target_cpu or target_pc:
            return f'استخدام المعالج حاليًا حوالي {psutil.cpu_percent(interval=0.1):.0f}٪.'
        if target_gpu:
            from core.hardware_sensors import read_nvidia_gpu
            usage=read_nvidia_gpu().get('gpu_load_percent')
            return f'استخدام كارت الشاشة حاليًا {usage}٪.' if usage is not None else 'استخدام كارت الشاشة مش متاح من التعريف حاليًا.'
    return None


# Avoid hijacking imperative instructions such as "افتح إعدادات ويندوز".
_QUERY=re.compile(r'(?:مواصفات\s+(?:الجهاز|الكمبيوتر|اللابتوب)|\b(?:الرام|رام|الذاكرة|الذاكره|ram)\b|'
    r'\b(?:cpu|المعالج|البروسيسور|معالجي|معالج)\b|'
    r'(?:windows|ويندوز).{0,50}(?:اصدار|نسخة|كام|ايه|عندي)|'
    r'(?:اصدار|نسخة).{0,50}(?:windows|ويندوز)|'
    r'(?:الهارد|المساحة|الديسك|التخزين)|(?:البطارية|البطاريه|الشحن)|'
    r'(?:حرار|سخون|سخن|temperature|\btemp\b|\bload\b|استهلاك|ضغط|استخدام)|'
    r'(?:(?:ال)?برامج\s+(?:ال)?(?:شغالة|شغاله|مفتوحة)|(?:ال)?عمليات\s+(?:ال)?شغالة)|'
    r'(?:معلومات\s+(?:الجهاز|النظام))|(?:system\s+info|computer\s+specs))',re.I)
_IMPERATIVE=re.compile(r'^\s*(?:افتح|شغل|شغّل|ثبت|نزل|امسح|احذف|غيّر|غير|اعمل|نفذ|صلح|اكتب|ابني|ارسم|ترجم|ترجمة|لخص|اشرح|صحح|open|install|delete|run|create|translate|summarize)\b',re.I)


def answer(question: str) -> str | None:
    if platform.system() != 'Windows' or len(question)>240 or '\n' in question:
        return None
    q=question.strip()
    if not _QUERY.search(q) or _IMPERATIVE.search(q):return None
    # Read-only hardware measurement is explicitly requested in the question;
    # it never unlocks file, browser, process, or window automation.
    if is_temperature_request(q):
        sensor_result=_answer_sensor_question(q)
        if sensor_result is not None:return sensor_result
    if _THERMAL.search(q.lower()):return None
    if not _is_enabled():
        return 'أقدر أقرأ حالة ويندوز وأجاوبك من جهازك، بس لازم تفعّل «تفاعل برق مع الكمبيوتر» من الإعدادات الأول.'
    sensor_result=_answer_sensor_question(q)
    if sensor_result is not None:return sensor_result
    facts=snapshot()
    q=q.lower().replace('أ','ا').replace('إ','ا')
    if 'بطار' in q or 'شحن' in q:
        return (f"البطارية {facts['battery_percent']}٪، " + ('على الشاحن.' if facts['charging'] else 'مش على الشاحن.')) if 'battery_percent' in facts else 'مش قادر أقرأ حالة البطارية من ويندوز حاليًا.'
    if re.search(r'\b(?:الرام|رام|ram|الذاكره|الذاكرة|ذاكره|ذاكرة)\b',q):
        return f"جهازك فيه {facts.get('ram_gb','غير معروف')} جيجا رام، والمتاح حاليًا {facts.get('ram_available_gb','غير معروف')} جيجا."
    if any(t in q for t in ('هارد','مساح','تخزين','ديسك')):
        if not facts.get('drives'):return 'مش قادر أقرأ مساحة الأقراص دلوقتي.'
        return 'مساحة الأقراص: '+ '، '.join(f"{d['drive']}: فاضي {d['free_gb']} من {d['total_gb']} جيجا" for d in facts['drives']) + '.'
    if any(t in q for t in ('بطاريه',)):
        return 'مش قادر أقرأ حالة البطارية حاليًا.'
    if re.search(r'(?:(?:ال)?برامج\s+(?:ال)?(?:شغال|مفتوح)|(?:ال)?عمليات\s+(?:ال)?شغال)',q):
        apps=[a for a in facts.get('process_names',[]) if not a.lower().endswith(('host.exe','service.exe'))][:20]
        return 'من البرامج اللي شغالة حاليًا: '+('، '.join(apps) if apps else 'مش قادر أحددها')+'.'
    if any(t in q for t in ('cpu','المعالج','بروسيسور','معالجي')):
        return f"المعالج: {facts['cpu']}، بعدد {facts['logical_cpu_count']} معالج منطقي."
    if 'ويندوز' in q or 'windows' in q:
        return f"إصدار النظام على جهازك: {facts['operating_system']} {facts['windows_version']} ({facts['architecture']})."
    if any(t in q for t in ('مواصفات','معلومات الجهاز','معلومات النظام','system info','computer specs')):
        return (f"جهازك شغال على {facts['operating_system']} {facts['windows_version']}، "
                f"المعالج {facts['cpu']}، والرام {facts.get('ram_gb','غير معروف')} جيجا. "
                "تقدر تسألني عن الرام أو التخزين أو البطارية بالتحديد.")
    return None


def local_install_paths() -> dict:
    """Informational locations, no probing or file reads beyond pathlib."""
    from core.paths import data_dir, resource
    app_root = Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else resource()
    return {'application':str(app_root),'user_data':str(data_dir()),
            'wake_model':str(app_root/'models'/'wake'/'vosk-model-ar-mgb2-0.4'),
            'note':'Installed program binaries live in the selected installer folder. Mutable chat/settings remain in user data for upgrade safety.'}
