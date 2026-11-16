"""Audited, fully offline voice calculator and unit conversion utilities."""
from __future__ import annotations
import ast
import math
import operator

_OPS = {ast.Add:operator.add, ast.Sub:operator.sub, ast.Mult:operator.mul,
        ast.Div:operator.truediv, ast.Mod:operator.mod, ast.USub:operator.neg, ast.UAdd:operator.pos}


def calculate(expression: str) -> dict:
    if not isinstance(expression, str) or not 1 <= len(expression.strip()) <= 100:
        return {'status':'denied','message':'قول عملية حسابية قصيرة وواضحة.'}
    try:
        node=ast.parse(expression, mode='eval')
        if sum(1 for _ in ast.walk(node)) > 45:
            raise ValueError('large expression')
        def compute(item, depth=0):
            if depth > 12:raise ValueError('expression too deep')
            if isinstance(item, ast.Expression):return compute(item.body,depth+1)
            if isinstance(item, ast.Constant) and type(item.value) in (int,float):
                result=float(item.value)
                if not math.isfinite(result) or abs(result)>1e12:raise ValueError('out of range')
                return result
            if isinstance(item, ast.BinOp) and type(item.op) in _OPS:
                a,b=compute(item.left,depth+1),compute(item.right,depth+1)
                return _OPS[type(item.op)](a,b)
            if isinstance(item, ast.UnaryOp) and type(item.op) in _OPS:
                return _OPS[type(item.op)](compute(item.operand,depth+1))
            raise ValueError('unsupported syntax')
        value=compute(node)
        if not math.isfinite(value) or abs(value)>1e12:raise ValueError('out of range')
        return {'status':'ok','result':int(value) if value.is_integer() else round(value,8),
                'message':f'الناتج {int(value) if value.is_integer() else round(value,8)}'}
    except (SyntaxError,ValueError,ZeroDivisionError,OverflowError,TypeError):
        return {'status':'denied','message':'مسموح بالجمع والطرح والضرب والقسمة وباقي القسمة فقط، من غير معادلات كبيرة.'}

# Only dimension-compatible, exact fixed factors. No FX rates masquerading as live data.
_FACTORS={
 'km':('length',1000),'m':('length',1),'cm':('length',.01),'mi':('length',1609.344),
 'ft':('length',.3048),'in':('length',.0254),
 'kg':('mass',1),'g':('mass',.001),'lb':('mass',.45359237),
 'l':('volume',1),'ml':('volume',.001),'gal':('volume',3.785411784),
 'h':('time',3600),'min':('time',60),'s':('time',1),
}

def convert(value: float, from_unit: str, to_unit: str) -> dict:
    if type(value) not in (int,float) or not math.isfinite(value) or abs(value)>1e9:
        return {'status':'denied','message':'الكمية المطلوبة غير صالحة.'}
    if not isinstance(from_unit,str) or not isinstance(to_unit,str):
        return {'status':'denied','message':'الوحدة مش معروفة.'}
    src,dst=from_unit.strip().lower(),to_unit.strip().lower()
    if src in ('c','f') and dst in ('c','f'):
        result=value if src==dst else (value*9/5+32 if src=='c' else (value-32)*5/9)
    elif src in _FACTORS and dst in _FACTORS and _FACTORS[src][0]==_FACTORS[dst][0]:
        result=value*_FACTORS[src][1]/_FACTORS[dst][1]
    else:return {'status':'denied','message':'التحويل بين الوحدتين غير مدعوم أو غير متوافق.'}
    return {'status':'ok','result':round(result,6),'from':src,'to':dst,
            'message':f'{value:g} {src} تساوي {result:.6g} {dst}'}


def local_clock() -> dict:
    """Read only the computer's local clock; never invent timezone from IP."""
    from datetime import datetime
    clock=datetime.now().astimezone()
    return {'status':'ok','iso_local':clock.isoformat(timespec='seconds'),
            'timezone':clock.tzname() or 'local',
            'message':f'وقت الكمبيوتر المحلي دلوقتي {clock.strftime("%H:%M")}، بتاريخ {clock.strftime("%Y-%m-%d")}. التوقيت حسب إعدادات جهازك.'}
