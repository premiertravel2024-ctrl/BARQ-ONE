"""MCP stdio JSON-RPC client; process never receives arbitrary browser command lines."""
import asyncio, json, os, shutil, sys
from dataclasses import dataclass
from pathlib import Path
from core.security import child_env
from core.paths import state_file

class MCPError(Exception):pass
@dataclass
class MCPServer:
    id:str
    command:str
    args:list[str]
    enabled:bool=False
    timeout:int=60

# Pin a documented release. Upgrades are user-reviewed, not silent.
SERVERS={'rea':MCPServer('rea','npx',['-y','rea-agents@6.7.0','mcp'],False,90)}

def save_settings():
    data=[{'id':s.id,'command':s.command,'args':s.args,'enabled':s.enabled,'timeout':s.timeout} for s in SERVERS.values()]
    target=state_file('mcp-servers.json')
    target.write_text(json.dumps(data,indent=2),encoding='utf-8')

def load_settings():
    target=state_file('mcp-servers.json')
    if not target.is_file():return
    try:
        entries=json.loads(target.read_text(encoding='utf-8'))
        for entry in entries:
            if entry['id']=='rea':
                # Official pin and args are never overridden by local settings.
                SERVERS['rea'].enabled=bool(entry.get('enabled',False))
            elif entry['id'] not in ('windows-mcp','windows_mcp'):
                register(entry['id'],entry['command'],entry['args'],entry.get('enabled',False),persist=False)
    except (ValueError,KeyError,TypeError):pass

def register(id,command,args,enabled=False,persist=True):
    import re
    if not re.fullmatch(r'[a-z][a-z0-9_-]{2,40}',id) or id in ('rea','windows-mcp','windows_mcp'):raise MCPError('Invalid or reserved server ID')
    if any('windows-mcp' in str(a).lower() or 'windows_mcp' in str(a).lower() for a in [command, *args]):
        raise MCPError('Windows-MCP must use BARQ Computer Control approvals, not generic MCP')
    if command not in ('npx','node','uvx','docker','python') and not (Path(command).is_file() and Path(command).is_absolute()):
        raise MCPError('Choose an installed executable or approved package runner')
    if not isinstance(args,list) or len(args)>30 or any(not isinstance(a,str) or len(a)>200 for a in args):
        raise MCPError('Invalid server arguments')
    if command=='npx' and any(not __import__('re').fullmatch(r'[a-zA-Z0-9@/._:=+\-]+',a) for a in args):
        raise MCPError('npx arguments must be plain package identifiers and flags (no shell metacharacters)')
    if command=='python' and any(a in ('-c','-m') for a in args):
        raise MCPError('Inline Python commands are not supported; use a reviewed script file')
    if command=='node' and any(a in ('-e','--eval') for a in args):
        raise MCPError('Inline Node.js evaluation is disabled')
    SERVERS[id]=MCPServer(id,command,args,bool(enabled),60)
    if persist:save_settings()
    return {'id':id,'registered':True,'enabled':bool(enabled)}

load_settings()

def available(server):
    return bool(shutil.which(server.command) or (os.name=='nt' and shutil.which(server.command+'.cmd')))

def describe():
    return [{'id':s.id,'enabled':s.enabled,'installed':available(s),'command':s.command,'args':s.args,'transport':'stdio'} for s in SERVERS.values()]

class Client:
    def __init__(self,server):
        self.server=server;self.proc=None;self.counter=0
    async def __aenter__(self):
        s=self.server
        if not s.enabled:raise MCPError('MCP server disabled; enable it in settings first')
        if not available(s):raise MCPError('Node.js/npx is not installed or unavailable')
        command=s.command; args=s.args
        if os.name=='nt' and command.lower()=='npx':
            command='cmd.exe';args=['/d','/c','npx',*s.args]
        self.proc=await asyncio.create_subprocess_exec(command,*args,env=child_env(),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,
            creationflags=getattr(__import__('subprocess'),'CREATE_NO_WINDOW',0))
        try:
            await self.rpc('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'ai-router-agent','version':'2.0'}},timeout=25)
            await self._send({'jsonrpc':'2.0','method':'notifications/initialized'})
        except Exception:
            await self.__aexit__(None,None,None)
            raise
        return self
    async def __aexit__(self,*unused):
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            try:await asyncio.wait_for(self.proc.wait(),timeout=3)
            except asyncio.TimeoutError:self.proc.kill();await self.proc.wait()
    async def _send(self,payload):
        self.proc.stdin.write((json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n').encode())
        await self.proc.stdin.drain()
    async def rpc(self,method,params=None,timeout=None):
        self.counter+=1; id=self.counter
        await self._send({'jsonrpc':'2.0','id':id,'method':method,'params':params or {}})
        async def wait():
            for _ in range(10000):
                line=await self.proc.stdout.readline()
                if not line:raise MCPError('MCP server closed before responding')
                if len(line)>8*1024*1024:raise MCPError('MCP response too large')
                try:body=json.loads(line)
                except (ValueError,UnicodeDecodeError):continue
                if body.get('id')!=id:continue
                if 'error' in body:raise MCPError(str(body['error'])[:600])
                return body.get('result',{})
            raise MCPError('MCP server emitted too many unrelated messages')
        try:return await asyncio.wait_for(wait(),timeout=timeout or self.server.timeout)
        except asyncio.TimeoutError as exc:raise MCPError('MCP server timed out') from exc

async def discover(server_id='rea'):
    s=SERVERS.get(server_id)
    if server_id in ('windows-mcp','windows_mcp') or (s and any('windows-mcp' in str(x).lower() or 'windows_mcp' in str(x).lower() for x in [s.command,*s.args])):
        raise MCPError('Use the secured Windows-MCP computer control adapter')
    if not s:raise MCPError('Unknown MCP server')
    async with Client(s) as client:
        result=await client.rpc('tools/list')
        return result.get('tools',[])

async def invoke(server_id,tool_name,arguments):
    s=SERVERS.get(server_id)
    if server_id in ('windows-mcp','windows_mcp') or (s and any('windows-mcp' in str(x).lower() or 'windows_mcp' in str(x).lower() for x in [s.command,*s.args])):
        raise MCPError('Windows-MCP actions require BARQ Computer Control approval')
    if not s:raise MCPError('Unknown MCP server')
    async with Client(s) as client:
        listing=(await client.rpc('tools/list')).get('tools',[])
        match=next((t for t in listing if t.get('name')==tool_name),None)
        if not match:raise MCPError('Tool was not advertised by MCP server')
        if not isinstance(arguments,dict):raise MCPError('Tool arguments must be an object')
        result=await client.rpc('tools/call',{'name':tool_name,'arguments':arguments},timeout=s.timeout)
        return result
