"""Bounded, cached TMDB metadata access. Credentials never leave the backend."""
from __future__ import annotations
import os
import threading
import time
from collections import OrderedDict
from datetime import date, timedelta
import httpx

_lock = threading.RLock()
_cache = OrderedDict()
_retry_at = 0.0

class CatalogError(Exception):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status

def token():
    value = os.getenv('TMDB_READ_TOKEN', '').strip()
    if value:
        return value
    try:
        import keyring
        return keyring.get_password('BARQ ONE', 'tmdb-read-token') or ''
    except Exception:
        return ''

def configure(value):
    # Validate before replacing the working credential.
    _fetch('configuration', {}, credential=value, cache=False)
    try:
        import keyring
        keyring.set_password('BARQ ONE', 'tmdb-read-token', value)
    except Exception as exc:
        raise CatalogError('Credential vault unavailable. Set TMDB_READ_TOKEN and restart BARQ.') from exc
    with _lock:
        _cache.clear()

def _fetch(path, params, credential=None, cache=True):
    global _retry_at
    secret = credential or token()
    if not secret:
        raise CatalogError('TMDB_SETUP_REQUIRED', 503)
    key = (path, tuple(sorted(params.items())))
    now = time.monotonic()
    with _lock:
        entry = _cache.get(key)
        if cache and entry and now-entry[0] < 600:
            _cache.move_to_end(key)
            return entry[1]
        if now < _retry_at:
            raise CatalogError('TMDB rate limit. Please retry shortly.', 429)
    try:
        with httpx.Client(timeout=12, follow_redirects=False) as client:
            response = client.get('https://api.themoviedb.org/3/'+path, params=params,
                                  headers={'Authorization': 'Bearer '+secret, 'Accept':'application/json'})
        if response.status_code == 429:
            try: delay = min(120, max(1, int(response.headers.get('retry-after','10'))))
            except ValueError: delay = 10
            with _lock: _retry_at = time.monotonic()+delay
            raise CatalogError('TMDB rate limit. Please retry shortly.', 429)
        if response.status_code in (401, 403):
            raise CatalogError('TMDB token rejected. Update the API Read Access Token in setup.', 401)
        if response.status_code == 404:
            raise CatalogError('Title unavailable.', 404)
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise CatalogError('Cannot reach TMDB. Check your connection and retry.') from exc
    if cache:
        with _lock:
            _cache[key] = (time.monotonic(), result)
            while len(_cache) > 256: _cache.popitem(last=False)
    return result

def image(path, size='w500'):
    return 'https://image.tmdb.org/t/p/'+size+path if isinstance(path,str) and path.startswith('/') else None

def title(row, kind):
    return dict(id=row['id'],kind=kind,title=row.get('title') or row.get('name') or '',
        overview=row.get('overview') or '',date=row.get('release_date') or row.get('first_air_date') or '',
        rating=row.get('vote_average') if row.get('vote_count',0)>0 else None,
        poster=image(row.get('poster_path')),backdrop=image(row.get('backdrop_path'),'w1280'),
        genres=row.get('genre_ids') or [g['id'] for g in row.get('genres',[])])

def browse(kind='movie', collection='popular', query='', page=1, language='ar-SA', genre=None, year=None, rating=0, anime=False):
    params={'language':language,'page':page,'include_adult':'false'}
    if query:
        path='search/'+kind
        params['query']=query
        if year: params['primary_release_year' if kind=='movie' else 'first_air_date_year']=year
    elif collection=='trending' and not (genre or year or rating or anime):
        path='trending/'+kind+'/week'
    else:
        path='discover/'+kind
        params['sort_by']='vote_average.desc' if collection=='top' else ('primary_release_date.desc' if kind=='movie' else 'first_air_date.desc') if collection=='recent' else 'popularity.desc'
        if collection=='top': params['vote_count.gte']=200
        if rating: params['vote_average.gte']=rating; params['vote_count.gte']=50
        if year: params['primary_release_year' if kind=='movie' else 'first_air_date_year']=year
        genres=[str(genre)] if genre else []
        if anime:
            genres.append('16'); params['with_original_language']='ja'
        if genres: params['with_genres']=','.join(dict.fromkeys(genres))
        if collection=='recent':
            key='primary_release_date' if kind=='movie' else 'first_air_date'
            params[key+'.lte']=date.today().isoformat()
            params[key+'.gte']=(date.today()-timedelta(days=365)).isoformat()
    data=_fetch(path,params)
    rows=data.get('results',[])
    if query:
        # TMDB search doesn't support these filters; filter the returned page honestly.
        rows=[r for r in rows if (not genre or genre in r.get('genre_ids',[])) and
              (not anime or (16 in r.get('genre_ids',[]) and r.get('original_language')=='ja')) and
              (not rating or r.get('vote_average',0)>=rating)]
    return {'results':[title(r,kind) for r in rows if not r.get('adult')], 'page':data.get('page',page),
            'total_pages':min(500,data.get('total_pages',0)), 'total_results':data.get('total_results',0),
            'filtered_page':bool(query and (genre or anime or rating))}

def details(kind, identifier, language):
    data=_fetch(f'{kind}/{identifier}',{'language':language,'append_to_response':'credits,recommendations'})
    return {**title(data,kind),'genre_names':[g['name'] for g in data.get('genres',[])],
            'runtime':data.get('runtime'), 'seasons':data.get('number_of_seasons'),
            'cast':[{'name':c['name'],'character':c.get('character',''),'photo':image(c.get('profile_path'),'w185')} for c in data.get('credits',{}).get('cast',[])[:12]],
            'related':[title(r,kind) for r in data.get('recommendations',{}).get('results',[])[:12] if not r.get('adult')]}
