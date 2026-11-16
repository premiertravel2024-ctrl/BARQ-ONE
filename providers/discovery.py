"""Authenticated cloud model discovery (read-only): no prompts, no billing and no secret output.

Only the configured provider receives its own credential. Calls are user-initiated
through /v1/cloud/check; listing the UI never triggers background cloud requests.
GET /models verifies key acceptance, not the user's billing tier or inference quota.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from router.config import key_for

# Keep network endpoints pinned. Never send user API keys to an arbitrary
# hostname from a hand-edited providers.yaml.
from router.config import bundled_providers
CLOUD_HOSTS = {name:urlsplit(info['base_url']).hostname for name,info in bundled_providers().items()
               if info.get('kind','cloud')=='cloud'}


def endpoint_for(provider):
    """Resolve the standard OpenAI-compatible /models endpoint without user input."""
    if provider.name not in CLOUD_HOSTS or provider.kind != 'cloud':
        raise ValueError('This provider cannot be checked as a public cloud provider')
    parsed = urlsplit(provider.base_url)
    if parsed.scheme != 'https' or parsed.hostname != CLOUD_HOSTS[provider.name] or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port not in (None, 443):
        raise ValueError('Untrusted provider endpoint; cloud keys were not sent')
    if '${' in provider.base_url:
        # The Cloudflare account ID is user-configurable, but a malformed one
        # must never change the host or path semantics.
        import os, re
        account = os.getenv('CLOUDFLARE_ACCOUNT_ID', '').strip()
        if not re.fullmatch(r'[a-fA-F0-9]{32}', account):
            raise ValueError('Cloudflare account ID is missing or invalid')
        url = provider.base_url.replace('${CLOUDFLARE_ACCOUNT_ID}', account)
    else:
        url = provider.base_url
    return url.rstrip('/') + '/models'


def _model_ids(data: object) -> list[str]:
    if not isinstance(data, dict) or not isinstance(data.get('data'), list):
        raise ValueError('Provider returned an unexpected models response')
    return list(dict.fromkeys(x['id'] for x in data['data'] if isinstance(x, dict) and isinstance(x.get('id'), str)
                              and 0 < len(x['id']) <= 180))[:1200]


def _available_models(provider, reported: list[str]) -> tuple[list[str], list[str]]:
    """No paid variants are ever discovered or added to routing."""
    known = [m.name for m in provider.models if m.enabled and m.free and m.name in reported]
    if provider.name == 'openrouter' and reported:
        # OpenRouter documents openrouter/free as an alias; /models does not
        # necessarily list virtual router aliases.
        known.extend(m.name for m in provider.models if m.name == 'openrouter/free')
    new_free = []
    if provider.name == 'openrouter':
        # Dynamic list, not hardcoded guessed IDs: some DeepSeek versions are paid.
        # Never list or route a paid variant simply because its name has "deepseek".
        free = {m for m in reported if m.endswith(':free') and m not in known}
        def rank(name: str) -> tuple[int, str]:
            n = name.lower()
            if 'deepseek' in n and 'base' not in n: return (0, n)
            if any(tag in n for tag in ('coder','coding','flint','minimax','qwen','devstral','glm')):
                return (1, n)
            if 'base' in n: return (3, n)
            return (2, n)
        new_free = sorted(free, key=rank)[:48]
    # Dynamic :free discoveries are informational only, not auto-routed.
    return list(dict.fromkeys(known)), new_free


def validated_chat_url(provider):
    """Cloud keys may only be sent to their canonical HTTPS API hosts."""
    return endpoint_for(provider)[:-len('/models')] + '/chat/completions'


def safe_status(code: int):
    if code in (401, 403):
        return 'auth_error', 'API key was rejected or lacks permission'
    if code == 402:
        return 'billing_blocked', 'Provider requested payment: disabled without spending money'
    if code == 429:
        return 'rate_limited', 'Provider rate limit reached; try again later'
    if code >= 500:
        return 'provider_error', f'Provider temporary error (HTTP {code})'
    return 'provider_error', f'Provider returned HTTP {code}'


@dataclass
class CloudInspector:
    statuses: dict[str, dict] = field(default_factory=dict)
    ttl_seconds: int = 600

    def cached(self, name: str):
        value = self.statuses.get(name)
        if not value or time.time() - value.get('checked_at',0) > self.ttl_seconds:
            return None
        return value.copy()

    def forget(self, name: str):
        self.statuses.pop(name, None)

    async def check(self, provider, *, timeout: float = 9, transport=None):
        key = key_for(provider) if provider.kind == 'cloud' else ''
        now = time.time()
        result = {'provider': provider.name, 'status': 'unverified', 'verified': False,
                  'models': [], 'free_models': [], 'checked_at': now,
                  'message': 'Not checked'}
        if not provider.enabled:
            result.update(status='disabled', message='Provider is disabled')
        elif not key:
            result.update(status='missing_key', message='Add a free API key in Models')
        else:
            try:
                url = endpoint_for(provider)
                kwargs = {'timeout': httpx.Timeout(timeout, connect=min(5, timeout)), 'follow_redirects': False}
                if transport is not None:
                    kwargs['transport'] = transport
                async with httpx.AsyncClient(**kwargs) as client:
                    response = await client.get(url, headers={'Authorization': 'Bearer ' + key,
                         'Accept': 'application/json'})
                    if response.status_code != 200:
                        code, message = safe_status(response.status_code)
                        result.update(status=code, message=message)
                        if response.status_code==402:
                            from router.free_policy import note_billing
                            note_billing(provider.name,402)
                    else:
                        ids = _model_ids(response.json())
                        known, free = _available_models(provider, ids)
                        if known or free:
                            result.update(status='verified', verified=True,
                                models=known, free_models=free,
                                message='API accepted credentials; model list retrieved (inference not yet tested)')
                        else:
                            result.update(status='no_models', verified=False,
                                message='API accepts this key, but no configured chat model was found')
            except ValueError as exc:
                result.update(status='config_error', message=str(exc)[:160])
            except (httpx.TimeoutException, httpx.NetworkError, httpx.ProxyError, httpx.RemoteProtocolError):
                result.update(status='network_error', message='Network connection failed or timed out')
            except (httpx.HTTPError, OSError):
                result.update(status='network_error', message='Cloud model discovery could not connect')
        # Do not include API response bodies or exception URLs in results/logs.
        self.statuses[provider.name] = result
        return result.copy()

    async def check_many(self, providers, *, timeout=9):
        cloud = [p for p in providers if p.kind == 'cloud']
        semaphore = asyncio.Semaphore(3)
        async def one(provider):
            async with semaphore:
                return await self.check(provider, timeout=timeout)
        return await asyncio.gather(*(one(p) for p in cloud))
