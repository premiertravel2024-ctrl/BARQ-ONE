"""Model management: validated writable provider settings without exposing keys."""
from pathlib import Path
import yaml
from core.paths import state_file,resource
from router.config import Config, merge_new_builtin_providers

def set_provider(provider,enabled=None,priority=None,confirm_billing=False):
    file=state_file('providers.yaml')
    original=file if file.exists() else resource('config','providers.yaml')
    data=merge_new_builtin_providers(yaml.safe_load(original.read_text(encoding='utf-8')))
    found=False
    for p in data['providers']:
        if p['name']==provider:
            found=True
            if enabled is not None:
                from router.free_policy import blocked,set_block
                if enabled and p.get('free_status')=='requires_payment_method':
                    raise ValueError('هذا المزود يتطلب وسيلة دفع ولا يمكن تفعيله')
                if enabled and p.get('free_status')=='unverified':
                    raise ValueError('لم يتم التحقق من مجانية هذا المزود بعد')
                if enabled and blocked(provider):
                    if not confirm_billing:raise ValueError('يجب تأكيد رفع حظر الدفع صراحةً')
                    set_block(provider,False)
                p['enabled']=bool(enabled)
            if priority is not None:
                if not 0<=priority<=100:raise ValueError('Priority must be 0-100')
                p['priority']=priority
            break
    if not found:raise ValueError('Unknown provider')
    Config.model_validate(data)
    tmp=file.with_suffix('.tmp')
    tmp.write_text(yaml.safe_dump(data,allow_unicode=True,sort_keys=False),encoding='utf-8')
    tmp.replace(file)
    return {'provider':provider,'updated':True}
