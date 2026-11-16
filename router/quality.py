import json

def acceptable(text,messages):
    if not isinstance(text,str) or not text.strip():return False
    request=str(messages[-1].get('content','')) if messages else ''
    if 'json' in request.lower():
        try:json.loads(text)
        except ValueError:return False
    return True
