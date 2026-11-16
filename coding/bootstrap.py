"""Conservative project starter. Never runs generated code or overwrites existing files."""
from pathlib import Path
import re
from workspace.manager import root_of


def scaffold(workspace: str, name: str = 'barq-app', kind: str = 'desktop_python') -> dict:
    """Create a small runnable starter in a NEW child folder after approval."""
    root = root_of(workspace)
    if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{1,45}', name):
        raise ValueError('Project name must be a simple 2-46 character folder name')
    if kind not in ('desktop_python', 'web_static'):
        raise ValueError('Unsupported project starter')
    target = root / name
    # No mutation if target already exists; no traversal or surprise overwrites.
    if target.exists() or target.is_symlink():
        raise ValueError('Project folder already exists. Choose another project name.')
    target.mkdir(mode=0o700)
    try:
        if kind == 'desktop_python':
            source = '''"""BARQ desktop app starter. Python standard library only."""
import tkinter as tk
from tkinter import ttk


def main():
    window = tk.Tk()
    window.title("BARQ App")
    window.geometry("840x520")
    window.configure(bg="#0F1115")
    frame = tk.Frame(window, bg="#0F1115", padx=32, pady=28)
    frame.pack(fill="both", expand=True)
    tk.Label(frame, text="أهلاً بيك في برنامجك", fg="white", bg="#0F1115",
             font=("Arial", 22, "bold")).pack(pady=16)
    status = tk.StringVar(value="البرنامج جاهز للتطوير")
    tk.Label(frame, textvariable=status, fg="#C9D2DD", bg="#0F1115").pack(pady=10)
    ttk.Button(frame, text="جرّب الزر", command=lambda: status.set("الزر بيشتغل ✅")).pack(pady=14)
    window.mainloop()


if __name__ == "__main__":
    main()
'''
            (target / 'main.py').write_text(source, encoding='utf-8')
            readme = '# BARQ desktop starter\n\nRun with `python main.py` (Python includes tkinter on standard Windows installations).\n\nThis is a runnable starter, not the finished custom app. Continue the task in BARQ to implement features.\n'
        else:
            page = '''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BARQ App</title><style>body{font-family:Arial,sans-serif;background:#0f1115;color:#f6f7fa;display:grid;place-items:center;min-height:100vh;margin:0}.card{padding:32px;border:1px solid #343944;border-radius:18px;background:#191d24;box-shadow:0 16px 60px #0004}button{background:#e8263e;border:0;border-radius:12px;color:white;padding:12px 22px;cursor:pointer}</style></head><body><div class="card"><h1>برنامجك بدأ يا معلم!</h1><p id="msg">واجهة مبدئية قابلة للتطوير</p><button id="action">جرّب</button></div><script>document.querySelector('#action').addEventListener('click',()=>document.querySelector('#msg').textContent='شغال!')</script></body></html>'''
            (target / 'index.html').write_text(page, encoding='utf-8')
            readme = '# BARQ web starter\n\nOpen `index.html` in a browser. This is an initial preview, not the finished custom app.\n'
        (target / 'README.md').write_text(readme, encoding='utf-8')
    except Exception:
        for child in target.iterdir():
            if child.is_file():
                child.unlink()
        target.rmdir()
        raise
    return {'created': True, 'project_path': str(target), 'files': [(target / ('main.py' if kind == 'desktop_python' else 'index.html')).name, 'README.md'], 'runnable_starter_only': True}
