"""Resolve music by name to official, embeddable provider pages."""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

import httpx

from services.web_research import ResearchError, _ddg_search

PROVIDERS = {
    'spotify': ('open.spotify.com', r'(track|album|playlist|artist)/([a-zA-Z0-9]{22})'),
    'anghami': ('play.anghami.com', r'(song|album|playlist|artist)/([0-9]{1,15})'),
}


def indexed_tracks(provider: str, query: str) -> list[dict]:
    host, pattern = PROVIDERS[provider]
    matches = {}
    terms = ' '.join(re.findall(r'[^\W_]+', query))
    if not terms:
        return []
    for result in _ddg_search(f'site:{host} {terms}'):
        try:
            url = urlsplit(result['url'])
        except ValueError:
            continue
        if url.scheme not in ('https', 'http') or url.netloc != host:
            continue
        path = url.path.removeprefix('/embed')
        match = re.fullmatch('/' + pattern + '/?', path)
        if not match:
            continue
        kind, identifier = match.groups()
        title = re.split(r'\s[|·]\s', result['title'], maxsplit=1)[0].strip()
        if title:
            matches[kind, identifier] = {'kind': kind, 'id': identifier, 'title': title}
    return list(matches.values())


def spotify_tracks(query: str, market: str) -> list[dict] | None:
    client_id = os.getenv('SPOTIFY_CLIENT_ID', '').strip()
    secret = os.getenv('SPOTIFY_CLIENT_SECRET', '').strip()
    if not client_id or not secret:
        return None
    with httpx.Client(timeout=5.0) as client:
        token = client.post('https://accounts.spotify.com/api/token',
                            data={'grant_type': 'client_credentials'}, auth=(client_id, secret))
        token.raise_for_status()
        response = client.get('https://api.spotify.com/v1/search',
                              params={'q': query, 'type': 'track,album,artist', 'market': market, 'limit': 5},
                              headers={'Authorization': 'Bearer ' + token.json()['access_token']})
        response.raise_for_status()
    matches = []
    data = response.json()
    for kind in ('track', 'album', 'artist'):
        for item in data.get(kind + 's', {}).get('items', []):
            identifier = item.get('id', '')
            title = item.get('name', '')
            if not title or not re.fullmatch(r'[a-zA-Z0-9]{22}', identifier):
                continue
            artists = ', '.join(artist.get('name', '') for artist in item.get('artists', []))
            images = (item.get('album') or item).get('images') or []
            image = images[-1].get('url', '') if images else ''
            matches.append({'kind': kind, 'id': identifier, 'title': title, 'artist': artists,
                            'artwork': image if re.fullmatch(r'https://i\.scdn\.co/image/[0-9a-f]+', image) else ''})
    return matches


def find_tracks(provider: str, query: str, market: str) -> dict:
    if provider == 'spotify':
        try:
            tracks = spotify_tracks(query, market)
        except (httpx.HTTPError, TypeError, ValueError, KeyError, AttributeError):
            tracks = None
        if tracks is not None:
            return {'items': tracks, 'source': 'provider'}
    try:
        return {'items': indexed_tracks(provider, query), 'source': 'index'}
    except ResearchError:
        return {'items': [], 'source': 'unavailable'}
