"""On-demand, read-only stats for an explicitly selected project process.
Requires psutil but makes no process, cloud or filesystem changes.
"""
from pathlib import Path
from workspace.manager import root_of


def inspect_pid(workspace: str, pid: int) -> dict:
    if not isinstance(pid, int) or pid < 2:
        raise ValueError('Invalid PID')
    try:
        import psutil
    except ImportError:
        return {'status': 'unavailable', 'note_ar': 'مراقبة العمليات تحتاج تثبيت psutil محليًا.'}
    root = root_of(workspace)
    try:
        proc = psutil.Process(pid)
        exe = proc.exe()
        working = proc.cwd()
        # Require the executable OR process cwd to be within the project root.
        if not (Path(exe).resolve().is_relative_to(root) or Path(working).resolve().is_relative_to(root)):
            raise ValueError('Process is outside the selected workspace')
        mem = proc.memory_info()
        return {'status': 'observed', 'pid': pid, 'name': proc.name()[:100],
                'memory_mb': round(mem.rss / (1024*1024), 1),
                'cpu_percent': round(proc.cpu_percent(interval=None), 1),
                'running': proc.is_running(), 'note_ar': 'قراءة واحدة بطلب المستخدم، مش مراقبة خلفية.'}
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as exc:
        raise ValueError('Cannot read selected process') from exc
