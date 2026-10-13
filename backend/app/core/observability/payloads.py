"""Parameter shape diagnostics, never request/response content or credentials."""
import re
from contextvars import ContextVar
from pydantic import BaseModel

redactions = ContextVar('diagnostic_redactions', default=())
SENSITIVE = re.compile(r'password|secret|authorization|cookie|api.?key|access.?token|refresh.?token|session|credential|private.?key', re.I)


def sensitive_values(value, depth=0):
    if depth > 4: return []
    if isinstance(value, BaseModel):
        try: value = value.model_dump(mode='python')
        except Exception: return []
    if not isinstance(value,dict): return []
    values=[]
    for key,item in list(value.items())[:40]:
        if SENSITIVE.search(str(key)):
            if isinstance(item,str): values.append(item[:8192])
            elif isinstance(item,(list,tuple)): values.extend(x[:8192] for x in item[:30] if isinstance(x,str))
        elif isinstance(item,(dict,BaseModel)): values.extend(sensitive_values(item,depth+1))
    return values[:32]


def redact(text, secrets=()):
    secrets=(*redactions.get(),*secrets)
    try:
        from app.core.config import settings
        secrets=(*secrets,*(v for k,v in vars(settings).items() if (SENSITIVE.search(k) or k.endswith('_key')) and isinstance(v,str) and v))
    except Exception: pass
    for value in secrets:
        if isinstance(value,str) and len(value)>=4: text=text.replace(value,'[REDACTED]')
    text=re.sub(r'data:[^\s"\']+','[BINARY OMITTED]',text,flags=re.I)
    text=re.sub(r'(?i)(bearer\s+)[\w.\-]+',r'\1[REDACTED]',text)
    text=re.sub(r'\b(?:sk-[\w-]{8,}|eyJ[\w-]+\.[\w-]+\.[\w-]+)\b','[REDACTED]',text)
    text=re.sub(r'(?i)((?:password|secret|api[ _-]?key|access[_-]?token)["\']?\s*[=:]\s*["\']?)[^\s,"\';}]+',r'\1[REDACTED]',text)
    text=re.sub(r'(?i)\b(?:secret|private)[-_]\S+','[REDACTED]',text)
    text=re.sub(r'(?i)\b[^\s"\']+[-_](?:secret|private)\b','[REDACTED]',text)
    text=re.sub(r'([a-z][a-z0-9+.-]*://)[^\s/@]+:[^\s/@]+@',r'\1[REDACTED]@',text,flags=re.I)
    return text


def capture(value, *, secrets=(), maximum=None):
    from app.core.config import settings
    if not settings.log_parameter_details: return dict(capture='disabled')
    nodes=0
    def shape(item,depth=0):
        nonlocal nodes
        nodes+=1
        kind=type(item).__name__
        if nodes>96: return dict(type=kind,detail='node_limit')
        if depth>4: return dict(type=kind,detail='depth_limit')
        if isinstance(item,BaseModel):
            fields=type(item).model_fields
            supplied=set(item.model_fields_set)
            keys=list(fields)[:32]
            return dict(type=kind,supplied=sorted(supplied),defaulted=sorted(set(fields)-supplied),
                fields={key:({'type':'redacted','present':key in supplied} if SENSITIVE.search(key) else shape(getattr(item,key),depth+1)) for key in keys},
                omitted_field_details=max(0,len(fields)-len(keys)))
        if item is None: return dict(type='null')
        if type(item) is bool: return dict(type='bool',value=item)
        if type(item) is str: return dict(type='str',characters=len(item),empty=not bool(item))
        if isinstance(item,bytes): return dict(type='bytes',length=len(item))
        if type(item) is dict:
            keys=[key for key in item if isinstance(key,str)][:32]
            result=dict(type='dict',supplied=keys,field_count=len(item),fields={key:
                ({'type':'redacted','present':True} if SENSITIVE.search(key) or key in ('key','token','headers') else shape(item[key],depth+1)) for key in keys},
                omitted_field_details=max(0,len(item)-len(keys)))
            for field in ('outcome','status','state','code'):
                status=item.get(field)
                if isinstance(status,str) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,79}',status): result[field]=status
            if item.get('outcome',item.get('status')) in ('failed','unavailable','rejected','timeout','budget_exhausted','invalid_input') and isinstance(item.get('reason'),str):
                result['failure_reason']=redact(item['reason'][:512],secrets)
            return result
        if type(item) in (list,tuple,set):
            first=next(iter(item),None)
            return dict(type=kind,count=len(item),empty=not bool(item),item_shape=shape(first,depth+1) if item else None)
        return dict(type=kind)
    try:
        result=shape(value)
        if isinstance(value,dict):
            for field in ('outcome','status','state','code'):
                status=value.get(field)
                if isinstance(status,str) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,79}',status):
                    result[field]=status
        return result
    except Exception: return dict(capture='unavailable')
