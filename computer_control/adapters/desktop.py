"""Windows-first OS control. Mouse automation requires an interactive desktop session.

Dependencies are imported lazily: package install and API smoke tests work headless.
"""
import os,sys,subprocess,webbrowser,time,io,shutil,hashlib
from pathlib import Path
from .base import OSAdapter,Perception

class WindowsAdapter(OSAdapter):
    def __init__(self):
        if sys.platform!='win32':raise RuntimeError('WindowsAdapter requires Windows')
    def _gui(self):
        try:
            import pyautogui as gui
        except ImportError as exc:raise RuntimeError('Install desktop dependencies: pip install -r requirements-computer-control.txt') from exc
        gui.FAILSAFE=True;gui.PAUSE=0.08
        return gui
    def check_folder_open(self):
        try:
            import comtypes.client
        except ImportError as exc:
            raise RuntimeError('أداة التحقق من نافذة الفولدر ناقصة. أصلح تثبيت برق.') from exc

    @staticmethod
    def _explorer_folder_visible(folder):
        """Ask Explorer for the exact local directory, not its window caption."""
        try:
            import comtypes
            from comtypes.client import CreateObject
            comtypes.CoInitialize()
            try:
                shell=CreateObject('Shell.Application',dynamic=True)
                expected=os.path.normcase(str(folder.resolve()))
                for _ in range(9):
                    for window in shell.Windows():
                        try:
                            path=Path(window.Document.Folder.Self.Path)
                            if path.is_absolute() and os.path.normcase(str(path.resolve()))==expected:
                                return True
                        except (OSError,ValueError,AttributeError,comtypes.COMError):
                            continue
                    time.sleep(.25)
            finally:
                comtypes.CoUninitialize()
        except (ImportError,OSError,AttributeError):
            return False
        except comtypes.COMError:
            return False
        return False

    def perceive(self):
        gui=self._gui();elements=[];title='';wins=[]
        try:
            import pywinauto
            desktop=pywinauto.Desktop(backend='uia')
            for i,win in enumerate(desktop.windows()[:30]):
                try:
                    name=win.window_text()
                    if name:wins.append(name[:160])
                except Exception:pass
            active=gui.getActiveWindow()
            title=(active.title or '') if active else ''
            if active and title:
                try:
                    win=desktop.window(title=title)
                    for index,control in enumerate(win.descendants()[:150]):
                        try:
                            r=control.rectangle();name=control.window_text() or ''
                            if not name and control.friendly_class_name() not in ('Edit','Button'):continue
                            if bool(getattr(control.element_info,'is_password',False)):continue
                            # Password controls are excluded entirely.
                            if control.element_info.control_type.lower()=='edit' and any(x in name.lower() for x in ('password','secret','token','key')):continue
                            role=control.element_info.control_type
                            rect=[r.left,r.top,r.right,r.bottom]
                            sig=self._signature(name,role,rect)
                            elements.append({'id':f'ui-{index}','name':name[:100],
                                'role':role,'rect':rect,'signature':sig})
                        except Exception:continue
                except Exception:pass
        except ImportError:
            active=gui.getActiveWindow();title=active.title if active else ''
        img=None;capture_bounds=None
        try:
            import mss
            from PIL import Image
            with mss.mss() as sct:
                monitor=sct.monitors[1]
                screenshot=sct.grab(monitor)
                capture_bounds=(monitor['left'],monitor['top'],monitor['width'],monitor['height'])
                image=Image.frombytes('RGB',screenshot.size,screenshot.rgb)
                image.thumbnail((1000,720))
                out=io.BytesIO();image.save(out,format='PNG');img=out.getvalue()
        except Exception:
            try:
                image=gui.screenshot()
                image.thumbnail((1000,720))
                out=io.BytesIO();image.save(out,format="PNG");img=out.getvalue()
            except Exception:pass
        pos=gui.position()
        return Perception(window=title,windows=wins,elements=elements,cursor=(int(pos.x),int(pos.y)),screenshot_png=img,screenshot_bounds=capture_bounds)
    @staticmethod
    def _signature(name,role,rect):
        return hashlib.sha256(repr((str(name)[:100],str(role),list(rect))).encode('utf-8')).hexdigest()[:24]
    def _uia_target(self,args):
        import pywinauto
        screen=self.perceive()
        # Current foreground window only; no stale target from another app/window.
        if args.get('window') and screen.window!=args['window']:
            raise RuntimeError('Active application changed; re-observe the screen')
        chosen=next((e for e in screen.elements if e['id']==args.get('element_id')),None)
        if not chosen or not args.get('signature') or chosen['signature']!=args['signature']:
            raise RuntimeError('Accessibility target changed; re-observe before clicking')
        if not screen.window:raise RuntimeError('No foreground window')
        window=pywinauto.Desktop(backend='uia').window(title=screen.window)
        # Element IDs come from same descendant-index space used in perceive().
        index=int(chosen['id'].removeprefix('ui-'))
        descendants=window.descendants()[:150]
        if not 0<=index<len(descendants):raise RuntimeError('UI element no longer available')
        element=descendants[index]
        if bool(getattr(element.element_info,'is_password',False)):
            raise PermissionError('Password inputs are not accessible')
        rect=element.rectangle()
        sig=self._signature(element.window_text() or '',element.element_info.control_type,
                             [rect.left,rect.top,rect.right,rect.bottom])
        if sig!=args['signature']:raise RuntimeError('UI control mismatch')
        return element
    def act(self,tool,args):
        gui=self._gui() if tool not in ('open_app','open_file','open_folder','open_with','open_url','invoke_ui','set_ui_text') else None
        if tool=='open_app':
            name=str(args.get('name') or args.get('path') or '')
            if not name:raise ValueError('Application name required')
            appid=args.get('appid')
            if appid:
                import re
                if not re.fullmatch(r'[a-zA-Z0-9_.!\-]{1,250}',str(appid)):
                    raise ValueError('Invalid AppUserModelId')
                subprocess.Popen(['explorer.exe','shell:AppsFolder\\'+str(appid)],shell=False)
                return {'ok':True,'action':tool}
            from computer_control.tools.app_index import resolve_app
            from computer_control.safety.policy import sensitive
            indexed=resolve_app(name)
            if indexed and indexed.get('appid'):
                appid=indexed['appid']
                subprocess.Popen(['explorer.exe','shell:AppsFolder\\'+str(appid)],shell=False)
            elif indexed and indexed.get('path'):
                location=str(indexed['path'])
                if location.lower().endswith('.lnk'):
                    os.startfile(location)
                elif not sensitive(location):
                    subprocess.Popen([location],shell=False)
                elif location in ('notepad.exe','calc.exe','explorer.exe','mspaint.exe'):
                    subprocess.Popen([location],shell=False)
                else:raise PermissionError('Application path requires an explicit user launch')
            elif shutil.which(name):subprocess.Popen([shutil.which(name)],shell=False)
            elif Path(name).is_file():os.startfile(name)
            else:raise FileNotFoundError('App not installed or ambiguous; specify installed application name')
        elif tool=='invoke_ui':
            element=self._uia_target(args)
            if element.element_info.control_type not in ('Button','MenuItem','Hyperlink','CheckBox','RadioButton'):
                raise ValueError('Only supported accessible controls can be invoked')
            element.invoke()
            return {'ok':True,'action':tool}
        elif tool=='set_ui_text':
            element=self._uia_target(args)
            if element.element_info.control_type!='Edit':
                raise ValueError('UI target is not an editable text field')
            element.set_edit_text(args['text'])
            return {'ok':True,'action':tool}
        elif tool=='open_file':os.startfile(str(args['path']))
        elif tool=='open_folder':
            folder=Path(args['path'])
            if not folder.is_dir():raise FileNotFoundError('Folder no longer exists')
            os.startfile(str(folder))
            return {'ok':True,'folder_visible':self._explorer_folder_visible(folder)}
        elif tool=='open_with':subprocess.Popen([str(args['app']),str(args['path'])],shell=False)
        elif tool=='open_url':
            if not webbrowser.open(str(args['url'])):raise RuntimeError('المتصفح ما قبلش طلب الفتح.')
        elif tool in ('click','double_click','hover'):
            x,y=self._point(args)
            if tool=='hover':gui.moveTo(x,y,duration=0.15)
            else:gui.click(x,y,clicks=2 if tool=='double_click' else 1,button=str(args.get('button','left')))
        elif tool=='drag':
            start=args.get('from');end=args.get('to')
            gui.moveTo(int(start[0]),int(start[1]));gui.dragTo(int(end[0]),int(end[1]),duration=0.4)
        elif tool=='scroll':gui.scroll(int(args.get('amount',1)))
        elif tool=='type_text':gui.write(str(args.get('text',''))[:3000],interval=min(.05,max(0,float(args.get('speed',0)))))
        elif tool=='paste':
            import pyperclip
            pyperclip.copy(str(args.get('text',''))[:10000]);gui.hotkey('ctrl','v')
        elif tool=='press_key':gui.press(str(args['key']))
        elif tool=='hotkey':gui.hotkey(*[str(x) for x in args.get('keys',[])][:4])
        elif tool in ('focus_window','minimize_window','maximize_window','close_window'):
            wins=gui.getWindowsWithTitle(str(args['title']))
            if len(wins)!=1:raise ValueError('Window title must uniquely identify one window')
            win=wins[0]
            {'focus_window':win.activate,'minimize_window':win.minimize,'maximize_window':win.maximize,'close_window':win.close}[tool]()
            if tool in ('minimize_window','maximize_window'):
                return {'ok':True,'action':tool,'window_state':bool(win.isMinimized if tool=='minimize_window' else win.isMaximized)}
            if tool=='close_window':
                return {'ok':True,'action':tool,'window_closed':not gui.getWindowsWithTitle(str(args['title']))}
        elif tool=='switch_window':gui.hotkey('alt','tab')
        elif tool=='close_app':
            import psutil
            name=str(args['name']).lower()
            hits=[p for p in psutil.process_iter(['name']) if str(p.info.get('name','')).lower()==name]
            if len(hits)!=1:raise ValueError('Process name must match exactly one process')
            hits[0].terminate() # never force kill without separate explicit approval
        elif tool=='set_volume':
            raise NotImplementedError('Volume control requires an OS-specific audio implementation')
        elif tool=='set_brightness':
            raise NotImplementedError('Brightness control requires an OS-specific display implementation')
        else:raise NotImplementedError(f'Adapter tool {tool} not available')
        return {'ok':True,'action':tool}
    def _point(self,args):
        if args.get('element_id'):
            tree=self.perceive().elements
            found=next((e for e in tree if e['id']==args['element_id']),None)
            if not found:raise ValueError('Element not present in current UI tree')
            if args.get('signature') and args['signature']!=found.get('signature'):
                raise RuntimeError('Stale UI element; refresh the desktop observation')
            a,b,c,d=found['rect'];return ((a+c)//2,(b+d)//2)
        return int(args['x']),int(args['y'])
    def check_abort(self):
        try:
            gui=self._gui();p=gui.position();return p.x==0 and p.y==0
        except Exception:return False

class MacAdapter(OSAdapter):
    def perceive(self):raise NotImplementedError('macOS Accessibility adapter is planned; not supported in this release')
    def act(self,tool,args):raise NotImplementedError('macOS control is not yet supported')
class LinuxAdapter(OSAdapter):
    def perceive(self):raise NotImplementedError('Linux X11 AT-SPI adapter is planned; not supported in this release')
    def act(self,tool,args):raise NotImplementedError('Linux control is not yet supported')

def default_adapter():
    if sys.platform=='win32':
        from .windows_mcp import MCPEnhancedAdapter
        return MCPEnhancedAdapter(WindowsAdapter())
    raise RuntimeError('Computer control is currently supported on Windows 10/11 only')
