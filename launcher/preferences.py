"""User-owned local launcher settings, not cloud configuration."""
from __future__ import annotations
import json
from pathlib import Path
from core.paths import state_file,resource
from computer_control.safety.policy import sensitive

DEFAULT={'voice_enabled':True,'stt':'gemini','speak_confirmation':'off','enabled':True,
         'apps':True,'files':True,'folders':True,'sites':True,'hide_paths_in_audit':True,
         'extra_roots':[], 'local_stt_model_path':''}

def load():
    values=DEFAULT.copy();p=state_file('launcher_preferences.json')
    if p.is_file():
        try:
            data=json.loads(p.read_text(encoding='utf-8'))
            values.update({k:v for k,v in data.items() if k in DEFAULT and type(v)==type(DEFAULT[k])})
        except (ValueError,OSError):pass
    return values

def save(values):
    updated=load()
    for key,val in values.items():
        if key not in DEFAULT or type(val)!=type(DEFAULT[key]):raise ValueError('Invalid launch setting')
        updated[key]=val
    if updated['stt'] not in ('gemini','local'):raise ValueError('Unrecognized STT engine')
    if updated['speak_confirmation'] not in ('off','system'):raise ValueError('Cloud speech replies are not auto-enabled')
    if len(updated['extra_roots'])>12 or any(not isinstance(p,str) or len(p)>500 for p in updated['extra_roots']):raise ValueError('Invalid roots')
    for folder in updated['extra_roots']:
        if sensitive(folder):raise ValueError('Protected folder cannot be indexed')
    path=state_file('launcher_preferences.json')
    path.write_text(json.dumps(updated,ensure_ascii=False,indent=2),encoding='utf-8')
    return updated
