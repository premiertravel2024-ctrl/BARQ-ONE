"""Local-only Ollama discovery. Never downloads models or calls Ollama cloud.

Only loopback addresses are accepted so a modified config cannot make the local
provider submit chat data to arbitrary hosts.
"""
import ipaddress
from urllib.parse import urlsplit
import httpx
from router.config import Model


def verified_base_url(raw: str) -> str:
    parsed = urlsplit(raw)
    if parsed.scheme != 'http' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Ollama must use an HTTP loopback address')
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        allowed = ip.is_loopback
    except ValueError:
        allowed = parsed.hostname.lower() == 'localhost'
    if not allowed or parsed.path.rstrip('/') not in ('', '/v1'):
        raise ValueError('Ollama must run on localhost, not a remote URL')
    try:
        port = parsed.port or 11434
    except ValueError as exc:
        raise ValueError('Invalid Ollama port') from exc
    if not 1 <= port <= 65535:
        raise ValueError('Invalid Ollama port')
    host = f'[{parsed.hostname}]' if ':' in parsed.hostname else parsed.hostname
    return f'http://{host}:{port}/v1'


def guess_strengths(name: str) -> list[str]:
    n = name.lower()
    strengths = ['writing', 'simple', 'arabic']
    if any(x in n for x in ('qwen', 'coder', 'code', 'deepseek', 'starcoder', 'gpt-oss')):
        strengths.extend(['coding', 'reasoning'])
    if any(x in n for x in ('r1', 'reason', 'thinking', 'gpt-oss')):
        strengths.append('reasoning')
    if any(x in n for x in ('vision', 'vl', 'llava')):
        strengths.append('vision')
    return list(dict.fromkeys(strengths))


def installed_model_names(data: dict) -> list[str]:
    """Read only downloaded *local* models; cloud entries are never a fallback."""
    found = []
    for item in data.get('models', []):
        if not isinstance(item, dict):
            continue
        name = item.get('name') or item.get('model')
        if not isinstance(name, str) or not name or len(name) > 160:
            continue
        lower = name.lower()
        if lower.endswith((':cloud', '-cloud')) or ':cloud-' in lower or '/cloud/' in lower:
            continue
        if name not in found:
            found.append(name)
    return found


async def discover_models(base_url: str, timeout: float = 1.4) -> list[Model]:
    base = verified_base_url(base_url)
    api_base = base[:-3]  # remove /v1
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), trust_env=False) as client:
        response = await client.get(api_base + '/api/tags')
        response.raise_for_status()
        models = installed_model_names(response.json())
    return [Model(name=name, strengths=guess_strengths(name), context_window=65536) for name in models]
