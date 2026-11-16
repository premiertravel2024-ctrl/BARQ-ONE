"""First-party, deterministic offline React/Vite recipe with evidence.

Never execute scripts from a downloaded project without a separate review gate.
"""
from __future__ import annotations
import json,re,time
from pathlib import Path
from .runner import Command,Runner,CommandRejected
from .grants import GrantStore
from .services import ServiceManager,choose_port

_TEMPLATE={
 'package.json':json.dumps({'name':'barq-react-project','version':'1.0.0','private':True,'type':'module',
    'scripts':{'dev':'vite --host 127.0.0.1','build':'vite build'},
    'dependencies':{'react':'^18.3.1','react-dom':'^18.3.1'},
    'devDependencies':{'vite':'^6.0.6','typescript':'^5.7.3','@vitejs/plugin-react':'^4.3.4'}},indent=2),
 'index.html':'<!doctype html><html lang="ar"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head><body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body></html>\n',
 'vite.config.ts':"import { defineConfig } from 'vite';\nimport react from '@vitejs/plugin-react';\nexport default defineConfig({ plugins: [react()], server: { host: '127.0.0.1', strictPort: true } });\n",
 'tsconfig.json':json.dumps({'compilerOptions':{'target':'ES2022','useDefineForClassFields':True,'lib':['ES2022','DOM','DOM.Iterable'],'module':'ESNext','skipLibCheck':True,'moduleResolution':'Bundler','allowImportingTsExtensions':True,'resolveJsonModule':True,'isolatedModules':True,'noEmit':True,'jsx':'react-jsx','strict':True},'include':['src']},indent=2),
 'src/main.tsx':"import React from 'react';\nimport { createRoot } from 'react-dom/client';\nimport './style.css';\ncreateRoot(document.getElementById('root')!).render(<React.StrictMode><h1>BARQ React — شغّال!</h1></React.StrictMode>);\n",
 'src/style.css':'body { margin: 2rem; font: 20px system-ui; background: #12151b; color: white; }\n',
 '.gitignore':'node_modules/\ndist/\n',
}

def scaffold_react(root:Path, grants:GrantStore, *, name='barq-react-app') ->dict:
    if not re.fullmatch(r'[a-z][a-z0-9_-]{1,48}',name):raise ValueError('Invalid project folder name')
    root=Path(root).resolve()
    dest=root/name
    if not grants.permits(str(dest),'create') or not grants.permits(str(dest),'write'):
        raise PermissionError('Explicit project grant with create + write scopes required')
    if dest.exists():
        raise FileExistsError('Existing project is never overwritten')
    dest.mkdir(parents=False)
    for name_,content in _TEMPLATE.items():
        path=dest/name_
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(content,encoding='utf-8')
    check=json.loads((dest/'package.json').read_text(encoding='utf-8'))
    if check['scripts']['build']!='vite build':raise RuntimeError('Template verification failed')
    return {'status':'verified','path':str(dest),'file_count':len(_TEMPLATE),'package':check['name']}

def install_and_build(project:Path,grants:GrantStore,runner:Runner,*,cancel=None)->dict:
    project=Path(project).resolve(strict=True)
    if not grants.permits(str(project),'install_dependencies') or not grants.permits(str(project),'build'):
        raise PermissionError('Project install_dependencies and build scopes required')
    manifest=json.loads((project/'package.json').read_text(encoding='utf-8'))
    if manifest.get('name')!='barq-react-project' or manifest.get('scripts',{}).get('build')!='vite build':
        raise PermissionError('Unknown/untrusted project manifest; requires independent approval')
    install=runner.run(Command('npm',('install','--ignore-scripts','--no-audit','--no-fund'),cwd=str(project)),cancel=cancel)
    if install.cancelled:raise InterruptedError('npm installation cancelled by user')
    if install.returncode!=0 or install.timed_out:raise RuntimeError('npm install failed: '+install.stderr[-800:])
    if not (project/'node_modules').is_dir():raise RuntimeError('npm reported success without node_modules')
    build=runner.run(Command('npm',('run','build'),cwd=str(project)),cancel=cancel)
    if build.cancelled:raise InterruptedError('Vite build cancelled by user')
    if build.returncode!=0 or build.timed_out:raise RuntimeError('Vite build failed: '+build.stderr[-800:])
    artifact=project/'dist'/'index.html'
    if not artifact.is_file():raise RuntimeError('Build did not produce dist/index.html')
    return {'status':'verified','path':str(project),'build_file':str(artifact),
            'install_seconds':install.duration,'build_seconds':build.duration}

def start_react(project:Path,grants:GrantStore,services:ServiceManager, *, port:int|None=None,cancel=None)->dict:
    project=Path(project).resolve(strict=True)
    if not grants.permits(str(project),'run_dev_server'):raise PermissionError('Run-server project grant required')
    if not (project/'node_modules'/'vite').exists():raise RuntimeError('Vite is not installed')
    port=port or choose_port()
    return services.start(project.name,Command('npm',('run','dev','--','--port',str(port),'--strictPort'),cwd=str(project)),
                          port=port,log_file=project/'.barq-dev-server.log',cancel=cancel)
