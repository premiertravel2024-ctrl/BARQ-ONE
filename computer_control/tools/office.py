"""Fixed Office automation: open Office or create one unsaved blank document.

No user text, paths, shell fragments, macros, saving or sending are accepted.
"""
from __future__ import annotations
import json
import subprocess
import sys

APPS={'excel':'Excel.Application','word':'Word.Application','powerpoint':'PowerPoint.Application'}


def validate_request(args:dict)->None:
    if not isinstance(args,dict) or set(args)!={'app','action'}:
        raise ValueError('Office routine accepts only app and action')
    if args['app'] not in APPS or args['action'] not in ('open','new'):
        raise ValueError('Unknown Office routine')


def script_for(args:dict)->str:
    validate_request(args)
    app=args['app']
    # All code is fixed product code; arguments select only these constants.
    create={
      'excel':"$doc=$app.Workbooks.Add(-4167); $app.UserControl=$true; $name=[string]$doc.Name; $verified=($app.Workbooks.Count -gt $before -and $doc.Worksheets.Count -ge 1)",
      'word':"$doc=$app.Documents.Add(); $name=[string]$doc.Name; $verified=($app.Documents.Count -gt $before)",
      'powerpoint':"$doc=$app.Presentations.Add(-1); $name=[string]$doc.Name; $verified=($app.Presentations.Count -gt $before)",
    }
    collection={'excel':'Workbooks','word':'Documents','powerpoint':'Presentations'}[app]
    operation=(f"$before=$app.{collection}.Count; "+create[app]) if args['action']=='new' else "$name=''; $verified=$true"
    return (
      "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
      "try { $app=[Runtime.InteropServices.Marshal]::GetActiveObject('"+APPS[app]+"') } "
      "catch { $app=New-Object -ComObject '"+APPS[app]+"' }; "
      "$app.Visible="+('$true' if app!='powerpoint' else '-1')+"; "+operation+"; "
      "if(-not $verified){throw 'Office did not confirm the requested document'}; "
      "[ordered]@{ok=$true;verified=$true;document_name=$name}|ConvertTo-Json -Compress"
    )


def perform(args:dict,*,runner=None)->dict:
    validate_request(args)
    if sys.platform!='win32':raise RuntimeError('Office routines require Windows and installed Microsoft Office')
    runner=runner or subprocess.run
    result=runner(['powershell.exe','-NoProfile','-NonInteractive','-Command',script_for(args)],
                  shell=False,capture_output=True,encoding='utf-8',errors='replace',timeout=35,
                  creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise RuntimeError('Office could not confirm the action. Check that the desktop app is installed and activated; no file was saved by BARQ.')
    try:response=json.loads(result.stdout.strip().lstrip('\ufeff'))
    except (ValueError,AttributeError):raise RuntimeError('Office returned no verified result; inspect the desktop before retrying')
    if not isinstance(response,dict) or response.get('ok') is not True or response.get('verified') is not True:
        raise RuntimeError('Office did not verify the operation')
    name=response.get('document_name','')
    if args['action']=='new' and (not isinstance(name,str) or not name.strip()):
        raise RuntimeError('Office did not return the new document name')
    return {'ok':True,'verified':True,'app':args['app'],'action':args['action'],
            'document_name':str(name)[:160],'saved':False}
