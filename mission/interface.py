"""Shared UI contract and conservative read-only checks; never a visual certification."""
import ast
from html.parser import HTMLParser
from workspace.manager import read_text

UI_CONTRACT = {
    'layout':'Choose hierarchy for the actual task: clear page title, one primary action, grouped secondary actions; avoid generic dashboard filler.',
    'system':'Define reusable colors, spacing, typography and component states in one theme module or stylesheet. Use an 8-unit spacing scale and readable type. Honor explicit user branding.',
    'states':['empty with a useful next action','loading without blocking the UI','error with recovery and preserved input','success only after real operation'],
    'interaction':'Every enabled control needs a real handler. Keyboard focus must remain visible; provide labels and a logical tab order. Confirm destructive actions.',
    'arabic':'For Arabic UI, use RTL reading order while keeping code, paths and numbers appropriately LTR. Use fonts actually available; provide fallbacks.',
    'resizing':'Support smaller windows without clipped actions: flexible layout, wrapping and scroll where needed; avoid fixed-position whole-screen layouts.',
    'desktop':'Keep network, long computation and file work off the UI thread; update widgets through the framework event loop. Never touch Tk widgets from workers.',
    'visual_quality':'Prefer balanced whitespace, restrained accent color, readable contrast, consistent component sizes, clear navigation and real content. Avoid fake statistics, noisy sidebars, repeated cards or decorative controls. Design for the target platform and user task.',
    'responsive_qa':'Document checks at narrow and wide window sizes; test keyboard-only navigation, input errors, focus, long text, empty lists, slow loading and multi-step workflows. A screenshot-only result is not functional proof.',
    'verification':'Test domain behavior independently. Document manual checks for keyboard, resizing, RTL, empty/error/loading states and real user workflows. Never claim visual review from static checks.'
}

class Markup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.ids={};self.labels=[];self.controls=[];self.images=[];self.issues=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs);line=self.getpos()[0]
        if attrs.get('id'):
            if attrs['id'] in self.ids:self.issues.append((line,'duplicate_ui_id','Duplicate HTML id: '+attrs['id']))
            self.ids[attrs['id']]=tag
        if tag=='label' and attrs.get('for'):self.labels.append((line,attrs['for']))
        if tag=='img' and 'alt' not in attrs:self.images.append(line)
        if tag in ('input','select','textarea') and attrs.get('type') not in ('hidden','submit','button','reset'):
            self.controls.append((line,attrs))
    handle_startendtag=handle_starttag


def review_interface(workspace,mission):
    issues=[];warnings=[];checked=0
    def finding(path,line,code,message):return {'path':path,'line':line,'code':code,'message':message}
    for row in mission['manifest']:
        path=row['path']
        if row.get('status') not in ('written','verified'):continue
        try:source=read_text(workspace,path)
        except (OSError,ValueError):continue
        if path.endswith('.html'):
            checked+=1;parser=Markup();parser.feed(source)
            issues.extend(finding(path,*item) for item in parser.issues)
            for line,target in parser.labels:
                if target not in parser.ids:issues.append(finding(path,line,'broken_label_target','Label points to missing id: '+target))
            linked={target for _,target in parser.labels}
            for line,attrs in parser.controls:
                if not(attrs.get('aria-label') or attrs.get('aria-labelledby') or attrs.get('id') in linked):
                    warnings.append(finding(path,line,'review_control_label','Verify accessible name; an enclosing label or dynamic label may supply it'))
            warnings.extend(finding(path,line,'missing_image_alt','Add alt text or empty alt for decorative images') for line in parser.images)
        elif path.endswith('.py'):
            try:tree=ast.parse(source)
            except SyntaxError:continue
            is_tk=any(isinstance(n,(ast.Import,ast.ImportFrom)) and ('tkinter' in (getattr(n,'module','') or '') or any(a.name=='tkinter' for a in n.names)) for n in ast.walk(tree))
            if not is_tk:continue
            checked+=1
            disabled={id(k) for call in ast.walk(tree) if isinstance(call,ast.Call) and any(k.arg=='state' and isinstance(k.value,ast.Constant) and k.value.value=='disabled' for k in call.keywords) for k in call.keywords}
            for node in ast.walk(tree):
                if id(node) not in disabled and isinstance(node,ast.keyword) and node.arg=='command' and isinstance(node.value,ast.Lambda) and isinstance(node.value.body,ast.Constant) and node.value.body.value is None:
                    issues.append(finding(path,node.lineno,'empty_ui_callback','UI command is lambda: None; implement behavior or disable the control with an explanation'))
    return {'passed':not issues,'checked_files':checked,'issues':issues[:40],'warnings':warnings[:40],
            'visual_verified':False,'scope':'Static HTML associations and obvious empty Tk callbacks only; visual layout, accessibility and workflows need runtime review'}
