"""Small, read-only public API hub. Never treat public-apis as an executable API.

Provider choices are hard-coded audited HTTPS endpoints; user input may name
packages/repos/cities but may never specify a URL, IP address, command or host.
No installations, code execution, private repository access or user-data upload.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_MAX_RESPONSE = 1_000_000
_TIMEOUT = 4.0
_TTL_SECONDS = 120
_cache: dict[tuple[str, str], tuple[float, dict]] = {}
_cache_lock = threading.RLock()


class LookupFailure(Exception):
    """Safe, short public-provider diagnostic for the UI and voice."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LookupFailure('المصدر غيّر عنوان الاتصال؛ برق منع التحويل لأسباب أمنية.')


# Privacy: no system proxy inference, no user IP geolocation, no custom endpoints.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _request(host: str, path: str, params: dict | None = None, accept='application/json') -> dict:
    if host not in {'pypi.org', 'registry.npmjs.org', 'api.github.com',
                    'geocoding-api.open-meteo.com', 'api.open-meteo.com'}:
        raise LookupFailure('المصدر الخارجي مش مسموح به.')
    url = 'https://' + host + path
    if params:
        url += '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'Accept': accept, 'User-Agent': 'BARQ-ReadOnly-API-Hub/1.0'})
    try:
        with _opener.open(req, timeout=_TIMEOUT) as resp:
            if resp.status != 200:
                raise LookupFailure('الخدمة الخارجية مش متاحة حاليًا.')
            length = resp.headers.get('Content-Length')
            if length and int(length) > _MAX_RESPONSE:
                raise LookupFailure('ردّ الخدمة كبير جدًا.')
            content = resp.read(_MAX_RESPONSE + 1)
            if len(content) > _MAX_RESPONSE:
                raise LookupFailure('ردّ الخدمة أكبر من الحد الآمن.')
            if 'json' not in resp.headers.get('Content-Type', ''):
                raise LookupFailure('ردّ الخدمة مش بصيغة JSON.')
            data = json.loads(content)
            if not isinstance(data, dict):
                raise LookupFailure('بيانات الخدمة غير متوقعة.')
            return data
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise LookupFailure('مش لاقي العنصر ده في المصدر الرسمي.') from exc
        if exc.code in (403, 429):
            raise LookupFailure('المصدر وصل لحد الطلبات المسموح بها؛ جرّب بعد شوية.') from exc
        raise LookupFailure('الخدمة الخارجية رجعت خطأ اتصال.') from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise LookupFailure('مش قادر أوصل للمصدر الخارجي حاليًا.') from exc


def _safe_name(name: str, pattern: str, limit: int = 100) -> str:
    if not isinstance(name, str) or not 1 <= len(name) <= limit or not re.fullmatch(pattern, name, re.ASCII):
        raise LookupFailure('اسم المكتبة أو المشروع غير صالح.')
    return name


def _text(value: Any, limit: int = 180) -> str:
    return str(value or '').replace('\n', ' ').replace('\r', ' ').strip()[:limit]


def _lookup(provider: str, target: str) -> dict:
    if provider == 'pypi':
        name = _safe_name(target, r'[A-Za-z0-9][A-Za-z0-9._-]*')
        data = _request('pypi.org', '/pypi/' + urllib.parse.quote(name, safe='') + '/json')
        info = data.get('info') or {}
        if not isinstance(info, dict): raise LookupFailure('بيانات المكتبة غير متوقعة.')
        return {'provider':'PyPI','name':_text(info.get('name') or name,100),
                'latest_version':_text(info.get('version'),45),
                'summary':_text(info.get('summary'),180),
                'python_requires':_text(info.get('requires_python'),90),
                'project_url':'https://pypi.org/project/' + urllib.parse.quote(name, safe='') + '/'}
    if provider == 'npm':
        name = _safe_name(target, r'(?:@[A-Za-z0-9][\w.-]*/)?[A-Za-z0-9][\w.-]*',120)
        # /<package>/latest avoids downloading the full package release history.
        pkg = urllib.parse.quote(name, safe='')
        data = _request('registry.npmjs.org', '/' + pkg + '/latest')
        return {'provider':'npm','name':_text(data.get('name') or name,120),
                'latest_version':_text(data.get('version'),45),
                'description':_text(data.get('description'),180),
                'license':_text(data.get('license'),75),
                'deprecated':_text(data.get('deprecated'),120),
                'package_url':'https://www.npmjs.com/package/' + urllib.parse.quote(name, safe='/@')}
    if provider == 'github':
        name = _safe_name(target, r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',180)
        owner,repo=name.split('/')
        if owner in ('.','..') or repo in ('.','..'):
            raise LookupFailure('اسم المستودع غير صحيح.')
        data = _request('api.github.com', '/repos/' + owner + '/' + repo)
        return {'provider':'GitHub','repository':name,'description':_text(data.get('description'),220),
                'default_branch':_text(data.get('default_branch'),80),
                'language':_text(data.get('language'),60),
                'stars':int(data.get('stargazers_count') or 0),
                'open_issues':int(data.get('open_issues_count') or 0),
                'archived':bool(data.get('archived')),
                'url':'https://github.com/' + name}
    if provider in ('weather', 'weather_forecast'):
        if not isinstance(target,str):
            raise LookupFailure('قول اسم المدينة عشان أجيب الطقس.')
        city = target.strip()
        if not 2 <= len(city) <= 80 or any(ch in city for ch in '/\\?#@'):
            raise LookupFailure('قول اسم المدينة عشان أجيب الطقس، من غير مشاركة موقعك الدقيق.')
        geo = _request('geocoding-api.open-meteo.com', '/v1/search',
                       {'name':city, 'count':1,'language':'ar','format':'json'})
        places = geo.get('results') or []
        if not places: raise LookupFailure('مش لاقي المدينة دي في خدمة الطقس.')
        place = places[0]
        lat,lon=place.get('latitude'),place.get('longitude')
        if not isinstance(lat,(float,int)) or not isinstance(lon,(float,int)):
            raise LookupFailure('إحداثيات المدينة مش متاحة.')
        query={'latitude':lat,'longitude':lon,
               'current':'temperature_2m,relative_humidity_2m,wind_speed_10m',
               'timezone':'auto'}
        if provider == 'weather_forecast':
            query.update({'daily':'temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code',
                          'forecast_days':3})
        weather = _request('api.open-meteo.com','/v1/forecast',query)
        current=weather.get('current') or {}
        if not isinstance(current.get('temperature_2m'),(float,int)):
            raise LookupFailure('قراءة الحرارة مش متاحة دلوقتي.')
        result={'provider':'Open-Meteo','city':_text(place.get('name') or city,75),
                'country':_text(place.get('country'),75),
                'temperature_c':current['temperature_2m'],
                'humidity_percent':current.get('relative_humidity_2m'),
                'wind_kmh':current.get('wind_speed_10m'),
                'observed_at':_text(current.get('time'),50),
                'notice':'Open-Meteo free access is limited to non-commercial use; check its licence before commercial deployment.'}
        if provider == 'weather_forecast':
            daily=weather.get('daily') or {}
            arrays=[daily.get(k) for k in ('time','temperature_2m_max','temperature_2m_min','precipitation_probability_max','weather_code')]
            if not all(isinstance(v,list) for v in arrays):
                raise LookupFailure('التوقعات مش متاحة من خدمة الطقس.')
            result['forecast']=[{'date':_text(day,24),'high_c':high,'low_c':low,
                                 'rain_probability_percent':rain,'weather_code':code}
                 for day,high,low,rain,code in list(zip(*arrays))[:3]
                 if isinstance(high,(int,float)) and isinstance(low,(int,float))]
            if not result['forecast']:
                raise LookupFailure('التوقعات مش متاحة من خدمة الطقس.')
        return result
    raise LookupFailure('نوع الخدمة مش مدعوم.')


def lookup(provider: str, target: str) -> dict:
    """Cached lookups, explicit request only. No retries that block the live call."""
    if provider not in {'pypi','npm','github','weather','weather_forecast'}:
        return {'status':'denied','message':'المصدر غير مدعوم.'}
    key=(provider, str(target))
    now=time.monotonic()
    with _cache_lock:
        saved=_cache.get(key)
        if saved and now-saved[0] < _TTL_SECONDS:
            return dict(saved[1])
        if len(_cache)>160:
            _cache.clear()
    try:
        result={'status':'ok','data':_lookup(provider,target)}
    except LookupFailure as exc:
        return {'status':'unavailable','message':str(exc)}
    with _cache_lock:
        _cache[key]=(time.monotonic(), result)
    return dict(result)


def describe(result: dict) -> str:
    if result.get('status')!='ok': return str(result.get('message') or 'المصدر مش متاح حاليًا.')
    d=result['data'];source=d.get('provider')
    if source=='PyPI':
        return f"مكتبة {d['name']} على PyPI آخر إصدار ليها {d['latest_version']}. {d['summary']} ومتطلبات بايثون: {d['python_requires'] or 'مش محددة'}."
    if source=='npm':
        return f"مكتبة {d['name']} على npm آخر إصدار ليها {d['latest_version']}. {d['description']}" + (f" تنبيه: {d['deprecated']}" if d['deprecated'] else '')
    if source=='GitHub':
        return f"مستودع {d['repository']} على GitHub؛ اللغة {d['language'] or 'غير محددة'}، و{d['stars']} نجمة. {d['description']}" + (' المستودع مؤرشف.' if d['archived'] else '')
    if source=='Open-Meteo':
        message=f"درجة الحرارة في {d['city']} {d['temperature_c']} مئوية، والرطوبة {d['humidity_percent']}٪، حسب Open-Meteo عند {d['observed_at']}."
        if d.get('forecast'):
            message+=' التوقعات: '+ '؛ '.join(f"{day['date']}: من {day['low_c']} إلى {day['high_c']} مئوية، فرصة المطر {day['rain_probability_percent']}٪" for day in d['forecast'])
        return message
    return 'مفيش نتيجة.'


def match_explicit_programming_question(message: str) -> tuple[str,str] | None:
    """Only intercept clear package/repository *metadata* questions, never coding commands."""
    if not isinstance(message,str) or len(message)>250 or '\n' in message:
        return None
    s=message.strip()
    if not re.search(r'اصدار|إصدار|نسخ[هة]|version|latest|بيانات|معلومات|info|release',s,re.I):
        return None
    for provider,pattern in (
        ('pypi',r'(?:PyPI|بايثون|python|pip)\s*[:\-]?\s*(?:ل?مكتبة\s*)?([A-Za-z0-9][A-Za-z0-9._-]{0,80})'),
        ('npm',r'(?:npm|جافاسكريبت|JavaScript)\s*[:\-]?\s*(?:ل?مكتبة\s*)?(@?[A-Za-z0-9][A-Za-z0-9_.\-/]{0,110})'),
        ('github',r'(?:GitHub|جيت.?هب)\s*[:\-]?\s*(?:ل?مستودع\s*)?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)')):
        match=re.search(pattern,s,re.I)
        if match:
            target=match.group(1).strip('.،؟? ')
            try:
                if provider=='pypi':_safe_name(target,r'[A-Za-z0-9][A-Za-z0-9._-]*')
                elif provider=='npm':_safe_name(target,r'(?:@[A-Za-z0-9][\w.-]*/)?[A-Za-z0-9][\w.-]*',120)
                else:_safe_name(target,r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',180)
            except LookupFailure: continue
            return provider,target
    return None
