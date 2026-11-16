"""Machine-readable tool parameter schema and validation, independent of LLM text."""
from computer_control.safety.policy import SUPPORTED
from typing import Any

REQUIRED={
 'office_document':{'app':str,'action':str},
 'read_screen':{},
 'list_apps':{},'find_ui_elements':{},
 'invoke_ui':{'element_id':str,'signature':str},'set_ui_text':{'element_id':str,'signature':str,'text':str},
 'open_app':{'name':str},'open_folder':{'path':str},'open_file':{'path':str},'open_with':{'path':str,'app':str},
 'close_app':{'name':str},'focus_window':{'title':str},'minimize_window':{'title':str},'maximize_window':{'title':str},'close_window':{'title':str},
 'click':{},'double_click':{},'hover':{},'drag':{'from':list,'to':list},'scroll':{'amount':int},
 'type_text':{'text':str},'paste':{'text':str},'press_key':{'key':str},'hotkey':{'keys':list},
 'list_dir':{'path':str},'read_file':{'path':str},'write_file':{'path':str,'text':str},
 'append_file':{'path':str,'text':str},'create_dir':{'path':str},
 'copy':{'src':str,'dst':str},'move':{'src':str,'dst':str},'rename':{'src':str,'dst':str},
 'search_files':{'path':str},'delete':{'path':str},'run_command':{'cmd':str},
 'clipboard_set':{'text':str},'open_url':{'url':str},
 'browser_fill':{'url':str,'selector':str,'value':str},
 'browser_submit':{'url':str,'selector':str},
 'download_file':{'url':str,'selector':str,'path':str},
 'wait_for':{'text':str},'set_volume':{'percent':int},'set_brightness':{'percent':int},'open_windows_settings':{'page':str},
}

def validate(tool:str,args:dict[str,Any]):
    if tool not in SUPPORTED:raise ValueError('Unknown tool')
    if not isinstance(args,dict):raise ValueError('Tool args must be object')
    if len(str(args))>100000:raise ValueError('Tool arguments too large')
    for key,kind in REQUIRED.get(tool,{}).items():
        if key not in args or not isinstance(args[key],kind):raise ValueError(f'{tool} requires {key}: {kind.__name__}')
    if tool=='office_document':
        from .office import validate_request
        validate_request(args)
    if tool in ('click','double_click','hover') and not args.get('element_id'):
        if not all(isinstance(args.get(k),int) for k in ('x','y')):raise ValueError('Click needs element_id or integer x,y')
    if tool in ('invoke_ui','set_ui_text'):
        if not args['element_id'].startswith('ui-') or len(args['signature'])!=24:
            raise ValueError('UI control requires a fresh signed accessibility target')
        if tool=='set_ui_text' and len(args['text'])>3000:
            raise ValueError('Too much text for a UI field')
    return args

def schemas()->list[dict]:
    return [{'name':tool,'parameters':{'type':'object','properties':{
        k:{'type':{'str':'string','int':'integer','list':'array'}[t.__name__]} for k,t in REQUIRED.get(tool,{}).items()},
        'required':list(REQUIRED.get(tool,{}))}} for tool in sorted(SUPPORTED)]
