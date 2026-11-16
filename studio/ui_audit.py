"""Conservative, read-only UI quality review of a user-selected workspace.

This is an evidence report, NOT a simulated browser, screenshot, accessibility
certification, or a declaration that a generated application works.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

from studio.project import tree
from workspace.manager import read_text
from mission.interface import review_interface

_UI_EXT={'.html','.htm','.css','.scss','.tsx','.jsx','.vue','.svelte','.qml','.ui'}
_MAX_FILES=75
_MAX_TEXT=220_000


def _finding(path:str,line:int,kind:str,message:str,severity:str='review')->dict:
    return {'file':path,'line':line,'kind':kind,'message':message,'severity':severity}


def inspect_ui(workspace:str)->dict:
    """No code execution, no network calls, bounded traversal; uses safe tree and reads."""
    catalog=tree(workspace)
    candidates=[r['path'] for r in catalog['items'] if not r['is_dir'] and
                PurePosixPath(r['path']).suffix.lower() in _UI_EXT]
    findings=[]
    observations={'responsive_files':[], 'rtl_files':[], 'labelled_controls':[],
                  'focus_styles':[], 'loading_states':[], 'error_states':[]}
    checked=0
    html_manifest=[]
    for name in candidates[:_MAX_FILES]:
        try:
            source=read_text(workspace,name)
        except (OSError,UnicodeError,ValueError):
            continue
        if len(source)>_MAX_TEXT:
            findings.append(_finding(name,1,'large_file','ملف كبير؛ تمت تخطي مراجعته الساكنة.'))
            continue
        checked+=1
        ext=PurePosixPath(name).suffix.lower()
        if ext in ('.html','.htm'):
            html_manifest.append({'path':name,'status':'written'})
        if re.search(r'@media|@container|\b(?:sm|md|lg|xl):|minmax\(|grid-template-columns|flex-wrap',source):
            observations['responsive_files'].append(name)
        if re.search(r'\bdir=["\']rtl|direction\s*:\s*rtl|\bdir=\{|\blogical\b|margin-inline|padding-inline',source):
            observations['rtl_files'].append(name)
        if re.search(r'aria-label|aria-labelledby|<label\b|htmlFor=',source):
            observations['labelled_controls'].append(name)
        if re.search(r':focus-visible|focus-visible:|focus:ring|outline-offset',source):
            observations['focus_styles'].append(name)
        if re.search(r'loading|isLoading|aria-busy|skeleton|جاري',source,re.I):
            observations['loading_states'].append(name)
        if re.search(r'catch\b|error|retry|خطأ|تعذّر|فشل',source,re.I):
            observations['error_states'].append(name)
        if ext in ('.tsx','.jsx','.vue','.svelte'):
            # Heuristic only: real accessible names can come from component props,
            # surrounding labels, and shared components. Never call these definite defects.
            for match in list(re.finditer(r'<img\b[^>]*>',source,re.I|re.S))[:15]:
                if not re.search(r'\balt\s*=',match.group(0)):
                    line=source.count('\n',0,match.start())+1
                    findings.append(_finding(name,line,'image_alt_review','راجع وجود alt للصورة؛ قد يكون الاسم من مكوّن أب.'))
            for match in list(re.finditer(r'<button\b.*?(?<![=])>',source,re.S))[:18]:
                tag=match.group(0)
                if len(tag)>2200:continue  # skip malformed or ambiguous JSX opening tags
                if re.search(r'\bonClick\s*=|\btype\s*=\s*["\']submit',tag) or 'disabled' in tag:
                    continue
                line=source.count('\n',0,match.start())+1
                findings.append(_finding(name,line,'button_handler_review','راجع سلوك الزر وربط إجراء حقيقي؛ قد يكون داخل form أو wrapper.'))
        if ext in ('.css','.scss'):
            if re.search(r'outline\s*:\s*(?:0|none)\s*[;}]',source,re.I) and ':focus-visible' not in source:
                findings.append(_finding(name,1,'focus_review','راجع إظهار تركيز الكيبورد عند إلغاء outline.'))
    html=review_interface(workspace,{'manifest':html_manifest}) if html_manifest else {'issues':[],'warnings':[],'checked_files':0}
    for item in html['issues']:
        findings.append(_finding(item['path'],item['line'],item['code'],item['message'],'issue'))
    for item in html['warnings']:
        findings.append(_finding(item['path'],item['line'],item['code'],item['message']))
    # These are recommendations, not claims about absence from the entire project.
    reminders=[]
    if checked and not observations['focus_styles']:
        reminders.append('راجع مؤشر تركيز الكيبورد عبر التطبيق أثناء التشغيل؛ لم يظهر دليل واضح ضمن الملفات المفحوصة.')
    if checked and not observations['responsive_files']:
        reminders.append('اختبر واجهة البرنامج على نافذة صغيرة؛ لم يُرصد نمط استجابة واضح ضمن الملفات المفحوصة.')
    reminders.extend([
        'اختبر فعليًا: التحميل والخطأ والحالة الفارغة والعودة من النافذة الفرعية.',
        'اختبر لوحة المفاتيح وقراءة الشاشة، العربية RTL، وتبديل حجم النافذة والتباين.',
        'لا يمكن تأكيد جمال التصميم أو تشغيل الأزرار باختبار ساكن؛ لازم تجربة تشغيل ولقطات شاشة.',
    ])
    return {'workspace':catalog['root'],'checked_files':checked,'total_ui_files':len(candidates),
            'truncated':len(candidates)>_MAX_FILES or bool(catalog['truncated']),
            'findings':findings[:90],'observations':{k:{'count':len(v),'examples':v[:4]} for k,v in observations.items()},
            'next_checks':reminders,'visual_verified':False,'runtime_verified':False,
            'scope':'bounded static UI audit; no browser run and no code execution'}
