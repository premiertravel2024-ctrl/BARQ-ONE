"""Bounded, reversible local tools; GUI actions use OSAdapter."""
from __future__ import annotations
from pathlib import Path
import os,shutil,subprocess,time,glob,threading
from typing import Any
from computer_control.adapters.base import OSAdapter
from computer_control.safety.policy import resolve_path,redact,READ

class Tools:
    def __init__(self,adapter:OSAdapter):self.adapter=adapter;self.undo=[];self._browser=None;self.cancel_event=threading.Event()
    def cancel(self):self.cancel_event.set()
    def copy_for_sequence(self,args):
        from computer_control.cognition import verify_action
        import tempfile

        if self.cancel_event.is_set():raise InterruptedError('Stopped by user')
        src=resolve_path(args['src']);dst=resolve_path(args['dst'])
        if not src.is_file():
            raise FileNotFoundError('الملف مش موجود بالاسم والامتداد المطلوبين في المجلد المحدد.')
        if dst.exists():
            if verify_action('copy',args,{}).status=='verified':
                return {'already_exists':True}
            raise FileExistsError('فيه ملف مختلف بنفس الاسم في الفولدر. النسخة الموجودة محفوظة.')

        # Publish only the complete copy. A concurrent destination creation
        # fails atomically on Windows without replacing the existing file.
        fd,temp=tempfile.mkstemp(prefix='.barq-copy-',dir=dst.parent)
        os.close(fd)
        try:
            shutil.copy2(src,temp)
            if self.cancel_event.is_set():raise InterruptedError('Stopped by user')
            if os.name=='nt':
                os.rename(temp,dst)
            else:
                os.link(temp,dst)
            self.undo.append(('unlink',str(dst)))
            return {'copied':str(dst)}
        finally:
            Path(temp).unlink(missing_ok=True)

    def act(self,tool:str,args:dict[str,Any]):
        if self.cancel_event.is_set():raise InterruptedError("Stopped by user")
        if tool=='office_document':
            from .office import perform
            return perform(args)
        if tool in {'get_volume','set_volume','get_brightness','set_brightness','open_windows_settings'}:
            from computer_control.tools import windows_quick
            if tool in {'get_volume','get_brightness'}:return getattr(windows_quick,tool)()
            if tool in {'set_volume','set_brightness'}:return getattr(windows_quick,tool)(args['percent'])
            return windows_quick.open_windows_settings(args['page'])
        if tool=='read_screen':
            from .screen import read_screen
            return read_screen(self.adapter)
        if tool=='observe':return {'perception':self.adapter.perceive().safe_data()}
        if tool=='find_ui_elements':
            screen=self.adapter.perceive().safe_data()
            query=str(args.get('query','')).casefold()[:100]
            return {'window':screen['window'],'elements':[e for e in screen['elements']
                if not query or query in str(e.get('name','')).casefold()][:80]}
        if tool=='list_apps':
            from launcher.indexes import Index
            matches=Index().apps()
            # Only application labels, never filesystem or token-bearing arguments.
            return {'apps':sorted({e['label'][:100] for e in matches if e.get('label')})[:250]}
        if tool=='list_windows':return {'windows':self.adapter.perceive().windows}
        if tool=='take_screenshot':
            p=self.adapter.perceive();return {'sha256':p.safe_data()['screenshot_hash'],'image_sent_to_cloud':False}
        if tool=='list_processes':
            import psutil
            return {'processes':[{'pid':p.info['pid'],'name':p.info.get('name')} for p in psutil.process_iter(['pid','name'])][:150]}
        if tool=='get_system_info':
            import platform
            return {'platform':platform.system(),'release':platform.release()}
        if tool=='list_dir':return {'entries':[{'name':p.name,'directory':p.is_dir()} for p in list(resolve_path(args['path']).iterdir())[:200]]}
        if tool=='read_file':return {'text':redact(resolve_path(args['path']).read_text(encoding='utf-8')[:20000])}
        if tool=='search_files':
            root=resolve_path(args['path']);pattern=str(args.get('glob','*'))
            return {'files':[str(p) for p in root.glob(pattern) if p.is_file()][:200]}
        if tool=='create_dir':
            p=resolve_path(args['path'])
            try:
                p.mkdir(parents=True,exist_ok=False)
            except FileExistsError:
                if not p.is_dir():raise
                return {'already_exists':True}
            self.undo.append(('rmdir',str(p)))
            return {'created':str(p)}
        if tool in ('write_file','append_file'):
            p=resolve_path(args['path']);if_exist=p.exists()
            if if_exist:
                import tempfile
                backup=Path(tempfile.mkdtemp(prefix='barq-undo-'))/p.name
                shutil.copy2(p,backup);self.undo.append(('restore',str(p),str(backup)))
            else:self.undo.append(('unlink',str(p)))
            text=str(args.get('text',''))[:200000]
            with p.open('a' if tool=='append_file' else 'w',encoding='utf-8') as f:f.write(text)
            return {'saved':str(p),'bytes':len(text.encode('utf-8'))}
        if tool=='copy':
            src=resolve_path(args['src']);dst=resolve_path(args['dst']);
            if dst.exists():raise FileExistsError('Destination exists; overwrite not allowed')
            if not src.is_file():raise ValueError('Copy supports files only')
            shutil.copy2(src,dst);self.undo.append(('unlink',str(dst)));return {'copied':str(dst)}
        if tool in ('rename','move'):
            src=resolve_path(args['src']);dst=resolve_path(args['dst']);
            if dst.exists():raise FileExistsError('Destination exists')
            src.rename(dst);self.undo.append(('move',str(dst),str(src)));return {'moved':str(dst)}
        if tool=='delete':
            from send2trash import send2trash
            p=resolve_path(args['path'])
            # send2trash recovery needs user interaction via OS Recycle Bin.
            send2trash(str(p));return {'sent_to_recycle_bin':str(p),'undo':'Restore using Windows Recycle Bin'}
        if tool=='run_command':
            # Compatibility only: legacy model action remains HIGH-risk and
            # must have a real on-screen approval before this path is reached.
            # The shared Runner uses CREATE_NO_WINDOW and shell=False on
            # Windows, instead of creating a visible command prompt here.
            # Parse once into program + argv. Never run the model string in a
            # shell or grant an arbitrary executable by its path.
            import shlex
            from execution.runner import Command, Runner
            command=str(args['cmd'])
            parts=shlex.split(command,posix=(os.name!='nt'))
            if not parts:raise ValueError('Empty command')
            if os.name=='nt':
                parts=[p[1:-1] if p.startswith('"') and p.endswith('"') else p for p in parts]
            cwd=str(resolve_path(args['cwd'])) if args.get('cwd') else None
            timeout=min(max(int(args.get('timeout',600)),1),1200)
            result=Runner().run(Command(parts[0],tuple(parts[1:]),cwd=cwd,
                                        timeout_total=timeout,timeout_idle=min(timeout,600)),
                                cancel=self.cancel_event)
            if result.cancelled:raise InterruptedError('Cancelled by user')
            if result.timed_out:raise TimeoutError('Command exceeded timeout')
            return {'exit_code':result.returncode,'stdout':redact(result.stdout[:6000]),
                    'stderr':redact(result.stderr[:3000]),'duration':result.duration,
                    'verified_process_exit':True}
        if tool in ('browser_fill','browser_submit','download_file'):
            from .browser import Browser
            if self._browser is None:self._browser=Browser()
            if tool=='browser_fill':return self._browser.fill(args['url'],args['selector'],args['value'])
            if tool=='browser_submit':return self._browser.submit(args['url'],args['selector'])
            return self._browser.download(args['url'],args['selector'],args['path'])
        if tool=='clipboard_get':
            import pyperclip
            return {'text':redact(pyperclip.paste()[:3000])}
        if tool=='clipboard_set':
            import pyperclip
            pyperclip.copy(str(args.get('text',''))[:10000]);return {'ok':True}
        if tool=='wait_for':
            target=str(args.get('text','')).lower();timeout=min(15,max(1,float(args.get('timeout',4))));start=time.monotonic()
            while time.monotonic()-start<timeout:
                screen=self.adapter.perceive()
                if any(target in str(e.get('name','')).lower() for e in screen.elements):return {'found':True}
                time.sleep(.25)
            return {'found':False}
        return self.adapter.act(tool,args)
    def undo_all(self):
        outcomes=[]
        while self.undo:outcomes.append(self.undo_last())
        return {"actions":outcomes,"undone":len(outcomes)}
    def undo_last(self):
        if not self.undo:return {'undone':False,'reason':'No recorded reversible action'}
        action,*items=self.undo.pop()
        if action=='unlink':resolve_path(items[0]).unlink(missing_ok=True)
        if action=='rmdir':resolve_path(items[0]).rmdir()
        if action=='restore':shutil.copy2(items[1],items[0])
        if action=='move':resolve_path(items[0]).rename(resolve_path(items[1]))
        return {'undone':True,'action':action}
