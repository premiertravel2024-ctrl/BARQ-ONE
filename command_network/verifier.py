"""Conservative cheap response checks; not a truthfulness guarantee."""
import json,re,ast
from dataclasses import dataclass
@dataclass(frozen=True)
class Check:
    accepted:bool
    confidence:float
    reason:str

def verify(text,profile):
    if not isinstance(text,str) or not text.strip():return Check(False,0,'empty reply')
    if profile.needs_json:
        try:json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip()))
        except (ValueError,TypeError):return Check(False,.1,'invalid JSON')
    if profile.language=='ar' and not profile.needs_json and not re.search(r'[\u0600-\u06ff]',text) and profile.task_type not in ('coding','debugging','translation'):
        return Check(False,.3,'requested Arabic, reply not Arabic')
    if len(text)>220_000:return Check(False,.2,'exceeds reply length budget')
    if re.match(r'(?i)^(?:as an ai language model|i cannot assist with that request)',text.strip()) and profile.risk=='low':
        return Check(False,.25,'generic refusal boilerplate on valid low-risk task')
    if profile.task_type in ('coding','debugging'):
        code=re.findall(r'```(?:python|py)\s*\n(.*?)```',text,re.S|re.I)
        for source in code:
            try:ast.parse(source)
            except SyntaxError:return Check(False,.3,'Python code block has a syntax error')
    if profile.language=='ar' and profile.task_type not in ('translation','extraction') and re.search(r'(?<!\w)(?:بدك|شو|بدي)(?!\w)',text):
        return Check(False,.45,'Arabic reply drifted from Egyptian persona')
    return Check(True,.75,'basic response validation passed; factual correctness not verified')
