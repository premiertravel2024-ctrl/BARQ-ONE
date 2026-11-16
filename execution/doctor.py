"""Offline capability probes: diagnose without modifying host settings."""
from __future__ import annotations
import os,platform,shutil,sys
from .runner import Runner,CommandRejected
from core.tool_locator import find_tool

TOOLS=('git','gh','python','py','node','npm','npx','pnpm','yarn','powershell','pwsh','winget','code')

def report()->dict:
    entries=[]
    for tool in TOOLS:
        try:
            path=Runner.resolve(tool)
            entries.append({'tool':tool,'status':'available','path':path})
        except CommandRejected:
            entries.append({'tool':tool,'status':'missing','reason':f'{tool} غير موجود في PATH؛ ثبته من مصدره الرسمي أولاً.'})
    disk=shutil.disk_usage(os.path.expanduser('~'))
    try:
        import ctypes
        admin=bool(ctypes.windll.shell32.IsUserAnAdmin()) if sys.platform=='win32' else False
    except (OSError,AttributeError):admin=False
    optional=[]
    for name in ('pywinauto','pyautogui','psutil'):
        try:
            import importlib.util
            ok=importlib.util.find_spec(name) is not None
        except (ImportError,ValueError):ok=False
        optional.append({'tool':name,'status':'available' if ok else 'missing',
                         'reason':'' if ok else 'Optional Windows control package is not installed'})
    try:
        from core.hardware_sensors import _monitor_executable
        monitor=_monitor_executable()
    except (ImportError,OSError):monitor=None
    optional.append({'tool':'LibreHardwareMonitor',
                     'status':'available' if monitor else 'missing',
                     'reason':'' if monitor else 'The signed sensor component was not found in BARQ installation'})
    # Installed via per-user Windows Toolkit; no PATH refresh required.
    mcp=find_tool('windows-mcp')
    optional.append({'tool':'Windows-MCP','status':'available' if mcp else 'missing',
                     'path':mcp or '', 'reason':'' if mcp else 'Install the official per-user Windows-MCP with BARQ Toolkit'})
    for name in ('uv','ffmpeg','rg','fd','7z'):
        path=find_tool(name)
        optional.append({'tool':name,'status':'available' if path else 'missing',
                         'path':path or '', 'reason':'' if path else 'Optional BARQ Toolkit component unavailable'})
    return {'platform':platform.platform(),'admin':admin,'disk_free_bytes':disk.free,
            'optional':optional,
            'tools':entries,'executed_installers':False,'network_used':False}
