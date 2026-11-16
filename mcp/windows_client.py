"""Private Windows-MCP stdio connection for BARQ computer control.

Third-party server is never bound to a network interface and is NOT exposed
through the generic /v1/mcp/run endpoint. BARQ's independent Policy must
approve each corresponding native action before this adapter is called.
"""
from __future__ import annotations
import asyncio
import concurrent.futures
import json
import os
from pathlib import Path
import sys
import threading
from computer_control.safety.policy import redact
from core.security import child_env

UPSTREAM_VERSION = '0.8.8'
# Defense-in-depth: no PowerShell, Registry, FileSystem, Process or Clipboard.
ALLOWED_TOOLS = ('Click', 'Type', 'Scroll', 'Move', 'Shortcut', 'App', 'Snapshot', 'ControlStatus')

class BridgeUnavailable(RuntimeError):
    """Tool has NOT been executed; native adapter may be used instead."""

class BridgeCallFailed(RuntimeError):
    """Tool may have been executed; must NOT replay using another adapter."""


def executable_path() -> Path | None:
    if sys.platform != 'win32':
        return None
    # uv tool install creates a per-user launcher at this *known* path.
    # Never accept a model-supplied executable, URL, host or command.
    base = Path.home() / '.local' / 'bin' / 'windows-mcp.exe'
    if base.is_file():
        return base
    return None


def installation_status() -> dict:
    binary = executable_path()
    return {
        'name': 'Windows-MCP', 'version_pinned': UPSTREAM_VERSION,
        'installed': bool(binary), 'transport': 'stdio',
        'security': 'local only; no shell, registry, filesystem or process tools',
        'requires_windows': True,
        'needs_internet_for_install': True,
        'requires_computer_control_consent': True,
        'source': 'https://github.com/CursorTouch/Windows-MCP',
        'install_command': 'scripts/install_windows_mcp.ps1 (included in BARQ Setup)',
    }


class WindowsMCPClient:
    """Lazily starts ONE reusable subprocess and sends serialized MCP requests.

    The dedicated background event loop keeps this process alive across multiple
    actions, avoiding the extra launch/handshake delay for every mouse click.
    """
    def __init__(self):
        self._loop = None
        self._thread = None
        self._proc = None
        self._lock = None
        self._sequence = 0
        self._tools = set()
        self._launch_guard = threading.Lock()
        self._disabled = False

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._lock = asyncio.Lock()
        self._loop.run_forever()

    def _ensure_loop(self):
        with self._launch_guard:
            if self._loop is not None and self._loop.is_running():
                return
            ready = threading.Event()
            def runner():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                self._lock = asyncio.Lock()
                ready.set()
                self._loop.run_forever()
            self._thread = threading.Thread(target=runner, name='BARQ-WindowsMCP-stdio', daemon=True)
            self._thread.start()
            if not ready.wait(2):
                raise BridgeUnavailable('Windows-MCP background loop did not start')

    async def _send(self, message):
        if not self._proc or not self._proc.stdin:
            raise BridgeUnavailable('Windows-MCP is not running')
        self._proc.stdin.write((json.dumps(message, ensure_ascii=False, separators=(',', ':'))+'\n').encode('utf-8'))
        await self._proc.stdin.drain()

    async def _rpc(self, method, params=None, timeout=15):
        self._sequence += 1
        request_id = self._sequence
        await self._send({'jsonrpc':'2.0','id':request_id,'method':method,'params':params or {}})
        async def read_response():
            for _ in range(300):
                line = await self._proc.stdout.readline()
                if not line:
                    raise BridgeCallFailed('Windows-MCP closed its pipe unexpectedly')
                if len(line) > 2_000_000:
                    raise BridgeCallFailed('Oversize Windows-MCP output')
                try:
                    payload = json.loads(line)
                except (UnicodeError, ValueError):
                    continue
                if payload.get('id') != request_id:
                    continue
                if payload.get('error'):
                    raise BridgeCallFailed(str(payload['error'])[:450])
                return payload.get('result', {})
            raise BridgeCallFailed('Too many unrelated Windows-MCP messages')
        try:
            return await asyncio.wait_for(read_response(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise BridgeCallFailed('Windows-MCP did not respond; action outcome unknown') from exc

    async def _start(self):
        if self._proc and self._proc.returncode is None:
            return
        binary = executable_path()
        if binary is None:
            raise BridgeUnavailable('Windows-MCP not installed; use native Windows control')
        env = child_env()
        env.update({
            'WINDOWS_MCP_TOOLS': ','.join(ALLOWED_TOOLS),
            'ANONYMIZED_TELEMETRY': 'false', 'POSTHOG_API_KEY': '',
            'WINDOWS_MCP_WATCHDOG': 'off',
        })
        # Absolute path, fixed arguments, no shell, no TCP listener.
        try:
            self._proc = await asyncio.create_subprocess_exec(
                str(binary), 'serve', '--transport', 'stdio',
                '--tools', ','.join(ALLOWED_TOOLS),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, env=env,
                limit=2_100_000,
                creationflags=getattr(__import__('subprocess'), 'CREATE_NO_WINDOW', 0),
            )
            await self._rpc('initialize', {
                'protocolVersion':'2025-03-26', 'capabilities':{},
                'clientInfo':{'name':'BARQ','version':'2.30.0'},
            }, timeout=20)
            await self._send({'jsonrpc':'2.0', 'method':'notifications/initialized'})
            discovered = await self._rpc('tools/list', timeout=15)
            self._tools = {t.get('name') for t in discovered.get('tools', [])}
            if not {'Click', 'Shortcut'}.issubset(self._tools):
                raise BridgeUnavailable('Windows-MCP did not expose expected desktop tools')
        except (OSError, BridgeCallFailed, BridgeUnavailable, asyncio.TimeoutError) as exc:
            await self._shutdown()
            raise BridgeUnavailable('Windows-MCP failed to initialize: '+str(exc)[:180]) from exc

    async def _shutdown(self):
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=2)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        self._proc = None
        self._tools = set()

    async def _call(self, name, params):
        async with self._lock:
            await self._start()
            if name not in self._tools:
                raise BridgeUnavailable('Windows-MCP tool unavailable: '+name)
            result = await self._rpc('tools/call', {'name':name,'arguments':params}, timeout=20)
            if result.get('isError'):
                raise BridgeCallFailed('Windows-MCP rejected action: '+redact(str(result.get('content', '')))[:300])
            # Never propagate raw images/embedded binary data to a model.
            parts = [str(c.get('text','')) for c in result.get('content',[]) if c.get('type') == 'text']
            return {'ok':True,'bridge':'Windows-MCP', 'tool':name,
                    'text':redact('\n'.join(parts))[:3500]}

    def call(self, name, params):
        if name not in ALLOWED_TOOLS or not isinstance(params, dict):
            raise BridgeUnavailable('Tool not part of reviewed Windows-MCP interface')
        if executable_path() is None:
            raise BridgeUnavailable('Windows-MCP executable missing')
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(self._call(name, params), self._loop)
        try:
            return future.result(timeout=42)
        except concurrent.futures.TimeoutError as exc:
            raise BridgeCallFailed('Windows-MCP operation timed out; outcome unknown') from exc

    def close(self):
        if self._loop and self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop).result(timeout=4)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)

