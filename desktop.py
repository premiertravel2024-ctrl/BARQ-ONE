"""Windows desktop launcher for the Python API and bundled React interface.

Use ``BARQ.exe --self-test C:/path/report.json`` to validate a frozen
build without starting a GUI or accessing third-party AI services.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path
from core.version import VERSION


# Keep an early fatal-exception log: a ctypes/Win32 access violation may kill
# BARQ.exe without raising a Python exception or running normal cleanup.
_crash_stream = None

def install_crash_diagnostics() -> None:
    global _crash_stream
    import faulthandler
    from core.paths import data_dir
    try:
        path = data_dir() / 'logs' / 'desktop-crash.log'
        path.parent.mkdir(parents=True, exist_ok=True)
        _crash_stream = path.open('a', encoding='utf-8', buffering=1)
        _crash_stream.write('\n--- BARQ desktop launch ' + time.strftime('%Y-%m-%d %H:%M:%S') + ' ---\n')
        faulthandler.enable(file=_crash_stream, all_threads=True)
        previous_thread_hook = threading.excepthook
        def report_thread_exception(args):
            try:
                traceback.print_exception(args.exc_type,args.exc_value,args.exc_traceback,file=_crash_stream)
            finally:
                previous_thread_hook(args)
        threading.excepthook = report_thread_exception
    except (OSError, RuntimeError):
        # A logging permission problem must not block startup.
        return

def log_desktop_event(message: str) -> None:
    if _crash_stream is not None:
        try:
            _crash_stream.write(time.strftime('%H:%M:%S ') + message[:250] + '\n')
        except OSError:
            pass


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def bundled_health_check() -> dict:
    """Verify resources, frozen imports, and local API. Never contact cloud services."""
    from fastapi.testclient import TestClient
    from core.paths import resource
    import webview  # ensure the bundled desktop renderer is importable
    import api
    from router.config import load_config

    required = [resource('web', 'index.html'), resource('config', 'providers.yaml'),
                resource('config', 'tools.yaml'), resource('assets', 'barq-tray-32.png')]
    # The proprietary UI font is optional. Existing Windows installs keep their
    # original copy; clean checkouts use their configured font fallback.
    missing = [str(x) for x in required if not x.is_file()]
    react = resource('web', 'react', 'index.html')
    if not react.is_file() or not (react.parent / 'assets').is_dir():
        missing.append('React production build (web/react/index.html and assets)')
    worklet = react.parent / 'audio' / 'live-capture.js'
    if not worklet.is_file() or worklet.stat().st_size < 100:
        missing.append('Live voice AudioWorklet (web/react/audio/live-capture.js)')
    if missing:
        raise RuntimeError('Missing packaged resources: ' + '; '.join(missing))
    # A successful UI/API smoke test alone used to miss the native microphone
    # runtime. Validate the actual frozen app before releasing an update.
    wake_runtime_bundled = False
    if getattr(sys, 'frozen', False):
        try:
            import numpy  # noqa: F401
            import vosk  # noqa: F401
            import sounddevice  # noqa: F401
            import pystray  # noqa: F401
            from PIL import Image  # noqa: F401
            from voice.wake_fingerprint import signature
            from array import array
            import math
            sample = array('h', (int(6000 * math.sin(i * 2 * math.pi * 440 / 16000))
                                 for i in range(10000))).tobytes()
            if signature(sample).shape != (36, 13):
                raise RuntimeError('Invalid bundled voice feature extractor')
            wake_runtime_bundled = True
        except (ImportError, OSError, ValueError, RuntimeError) as exc:
            raise RuntimeError('Packaged BARQ voice engine unavailable: ' + type(exc).__name__) from exc
    config = load_config()
    with TestClient(api.app) as client:
        responses = {endpoint: client.get(endpoint) for endpoint in
                     ('/', '/health', '/v1/performance', '/v1/tools', '/v1/router/providers', '/v1/computer/status')}
    failed = [f'{route}: HTTP {res.status_code}' for route,res in responses.items() if res.status_code != 200]
    with TestClient(api.app) as client:
        audio_response = client.get('/audio/live-capture.js')
    if (audio_response.status_code != 200
            or 'javascript' not in audio_response.headers.get('content-type', '').lower()
            or b"registerProcessor('barq-capture'" not in audio_response.content):
        raise RuntimeError('Live voice AudioWorklet HTTP endpoint is missing or invalid')
    if failed:
        raise RuntimeError('Local API failed: ' + '; '.join(failed))
    html = responses['/'].text
    if 'id="root"' not in html:
        raise RuntimeError('The app did not serve the React production entrypoint')
    # Exercise the frozen ASGI server on an actual loopback socket, including
    # first-task routing. Preparing a starter never writes project files.
    import tempfile
    import urllib.request
    import uvicorn
    port=free_port()
    server=uvicorn.Server(uvicorn.Config(api.app,host='127.0.0.1',port=port,log_level='error',access_log=False))
    thread=threading.Thread(target=server.run,daemon=True)
    thread.start()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        deadline=time.monotonic()+15
        while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.05)
        if not server.started:raise RuntimeError('Packaged HTTP server did not start')
        with opener.open(f'http://127.0.0.1:{port}/health',timeout=5) as response:
            if json.load(response).get('status')!='ok':raise RuntimeError('HTTP health failed')
        with opener.open(f'http://127.0.0.1:{port}/audio/live-capture.js', timeout=5) as response:
            body = response.read()
            if response.status != 200 or b"registerProcessor('barq-capture'" not in body:
                raise RuntimeError('Packaged Live voice worklet is not reachable from desktop HTTP server')
        with tempfile.TemporaryDirectory(prefix='barq-project-smoke-') as project:
            payload={'workspace':project,'conversation_id':'packaged-self-test',
                     'messages':[{'role':'user','content':'ابنيلي تطبيق موسيقى'}]}
            request=urllib.request.Request(f'http://127.0.0.1:{port}/v1/agent/prepare',
                data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with opener.open(request,timeout=10) as response:prepared=json.load(response)
            if prepared['plan']['steps'][0]['tool']!='project_bootstrap' or list(Path(project).iterdir()):
                raise RuntimeError('Main-chat planning or approval isolation failed')
    finally:
        server.should_exit=True
        thread.join(timeout=10)
        if thread.is_alive():raise RuntimeError('Local server did not shut down gracefully')
    return {'status': 'ok', 'version':VERSION,'frozen': bool(getattr(sys, 'frozen', False)),
            'ui': 'react', 'provider_config_entries': len(config.providers),
            'api_routes': {route: res.status_code for route,res in responses.items()},
            'webview_import': True,'voice_runtime_bundled':wake_runtime_bundled,
            'http_server':True,'live_voice_worklet':True,'main_chat_plan':True,'graceful_shutdown':True,
            'custom_font_available': resource('web','fonts','ge-ss-two-medium.otf').is_file()}


def write_self_test_report(filename: str) -> int:
    import tempfile
    previous=os.environ.get('AI_ROUTER_DATA_DIR')
    phase='initializing'
    try:
        # Build verification must never migrate or write the user's real state.
        with tempfile.TemporaryDirectory(prefix='barq-self-test-') as isolated:
            os.environ['AI_ROUTER_DATA_DIR']=isolated
            phase='health_check'
            report = bundled_health_check()
            phase='cleanup'
        report={**report,'cleanup_completed':True}
        status = 0
    except Exception as exc:
        report = {'status': 'error', 'exception': type(exc).__name__, 'phase':phase,'detail': str(exc)[:1500]}
        status = 1
    finally:
        if previous is None:os.environ.pop('AI_ROUTER_DATA_DIR',None)
        else:os.environ['AI_ROUTER_DATA_DIR']=previous
    path = Path(filename).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return status


def show_startup_error(exc: BaseException) -> None:
    """Notify users when WebView2 is absent or the local server fails to start."""
    from core.paths import data_dir
    log = data_dir() / 'logs' / 'startup.log'
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open('a', encoding='utf-8') as fp:
            fp.write(time.strftime('%Y-%m-%d %H:%M:%S') + '\n')
            traceback.print_exception(type(exc), exc, exc.__traceback__, file=fp)
    except OSError:
        pass
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None,
                'BARQ could not start.\n\n'
                'Check Microsoft Edge WebView2 Runtime and the application log at:\n'
                + str(log) + '\n\n' + str(exc)[:300],
                'BARQ — Startup error', 0x10)
        except Exception:
            pass


def run_desktop():
    from core.paths import data_dir
    install_crash_diagnostics()
    import uvicorn
    # Background wake is an explicit app setting. Permit BARQ's audio to play
    # without requiring a new browser click after every Windows login.
    if sys.platform=='win32':
        from voice.wake import wake_preferences
        if wake_preferences()['enabled']:
            existing=os.environ.get('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS','')
            if '--autoplay-policy=' not in existing:
                os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS']=(existing+' --autoplay-policy=no-user-gesture-required').strip()
    import webview
    import api

    port = free_port()
    config = uvicorn.Config(api.app, host='127.0.0.1', port=port,
                            log_level='warning', access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(120):
        if server.started:
            break
        if not thread.is_alive():
            break
        time.sleep(0.1)
    if not server.started:
        server.should_exit = True
        raise RuntimeError('Local BARQ service failed to start')
    from voice.wake import publish_endpoint, clear_endpoint
    publish_endpoint(port)
    from voice.wake import initialize_desktop_listener, stop_listener
    # Heavy Vosk model initialization must not compete with initial WebView UI.
    wake_boot_once = threading.Event()
    def start_wake_after_window_shown():
        if wake_boot_once.is_set():
            return
        wake_boot_once.set()
        threading.Thread(target=initialize_desktop_listener,
                         name='BARQ-Wake-Deferred-Startup', daemon=True).start()
    from voice.wake import run_wake_supervisor
    voice_monitor_stop = threading.Event()
    voice_monitor_thread = threading.Thread(target=run_wake_supervisor, args=(voice_monitor_stop,), daemon=True)
    voice_monitor_thread.start()
    glow_stop = threading.Event()
    from voice.screen_glow import run_glow
    from voice.wake import is_speaking
    glow_thread = threading.Thread(target=run_glow, args=(glow_stop,is_speaking), daemon=True)
    glow_thread.start()
    from services.personal_assistant import run_monitor
    from services.assistant_runtime import native_hotkey
    personal_stop=threading.Event()
    threading.Thread(target=run_monitor,args=(personal_stop,),daemon=True,name='BARQ-Personal-Monitor').start()
    threading.Thread(target=native_hotkey,args=(personal_stop,),daemon=True,name='BARQ-Emergency-Hotkey').start()
    from core.app_updates import UpdateBridge
    desktop_url = f'http://127.0.0.1:{port}'
    updates = UpdateBridge(desktop_url)
    try:
        window = webview.create_window('BARQ', desktop_url,
                              js_api=updates,
                              min_size=(950, 650), width=1350, height=860,
                              background_color='#0F1115')
        updates._window = window
        from voice.background_window import install as install_tray
        from voice.startup_greeting import maybe_greet_after_window_shown
        # The welcome runs only on the explicit Windows-login --background path.
        # It does not open a Live call or show the hidden desktop window.
        window.events.shown += maybe_greet_after_window_shown
        window.events.shown += start_wake_after_window_shown
        from core.paths import resource
        tray_enabled = install_tray(window, resource('assets', 'barq-tray-32.png'),
                                   start_hidden='--background' in sys.argv)
        if not tray_enabled and sys.platform == 'win32':
            # Do not pretend close-to-tray works if the tray dependencies broke.
            # A visible error avoids silently losing wake listening on window close.
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,
                'BARQ background tray could not start. Closing the window will exit BARQ. '
                'Repair the application to restore pystray/Pillow.',
                'BARQ background unavailable', 0x30)
        if '--background' in sys.argv and not tray_enabled:
            raise RuntimeError('Cannot start BARQ hidden: Windows tray is unavailable')
        log_desktop_event('WebView2 event loop starting')
        webview.start(gui='edgechromium', private_mode=False,
                      storage_path=str(data_dir() / 'webview'))
        log_desktop_event('WebView2 event loop returned: application window closed')
    finally:
        log_desktop_event('BARQ desktop shutting down; tray, wake, and HTTP server stopping')
        from voice.background_window import shutdown as shutdown_tray
        shutdown_tray()
        voice_monitor_stop.set()
        voice_monitor_thread.join(timeout=3)
        personal_stop.set()
        glow_stop.set()
        glow_thread.join(timeout=2)
        stop_listener()
        clear_endpoint()
        server.should_exit = True
        thread.join(timeout=10)
    return updates._pending



def apply_explicit_install_computer_consent() -> int:
    """Opt in to ordinary user-session desktop tools, never administrator rights.

    Called ONLY by an installer checkbox chosen by the user. Preserve existing
    allowlists and consent rules; don't start the GUI or the microphone here.
    """
    from core.paths import state_file
    path = state_file('computer_control_settings.json')
    try:
        data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        if not isinstance(data, dict):
            return 1
        # Explicit selection grants only the app's normal-user safe policy.
        data['enabled'] = True
        if data.get('mode') not in ('smart', 'ask-always', 'observe'):
            data['mode'] = 'smart'
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(path)
        return 0
    except (OSError, TypeError, ValueError):
        return 1

def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == '--barq-wallpaper-engine':
        from services.native_wallpaper import engine_main
        return engine_main(sys.argv[2], sys.argv[3])
    # Separate lightweight watchdog in the same frozen BARQ.exe. It never
    # launches the desktop UI, model engine, voice session, or local API.
    if len(sys.argv)==5 and sys.argv[1]=='--resource-saver-guardian':
        try:
            from services.resource_saver_guardian import main as guardian_main
            return guardian_main(sys.argv[2:])
        except (OSError,RuntimeError,ValueError):
            return 2
    if len(sys.argv)==2 and sys.argv[1]=='--setup-personal-assistant':
        try:
            from voice.background_autostart import configure
            from voice.wake import wake_config_path,wake_preferences
            import json
            if apply_explicit_install_computer_consent()!=0:return 1
            configure(True)
            prefs=wake_preferences();prefs.update(enabled=True,wake_computer_enabled=True,show_on_wake=False)
            path=wake_config_path();temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(prefs),encoding='utf-8');temporary.replace(path)
            return 0
        except (RuntimeError,OSError):return 1
    if len(sys.argv)==2 and sys.argv[1]=='--setup-background-start':
        try:
            from voice.background_autostart import configure
            configure(True)
            return 0
        except (RuntimeError, OSError):
            return 1
    if len(sys.argv)==2 and sys.argv[1]=='--setup-computer-consent':
        return apply_explicit_install_computer_consent()
    if len(sys.argv)==2 and sys.argv[1]=='--version':
        print('BARQ '+VERSION)
        return 0
    if len(sys.argv) >= 2 and sys.argv[1] == '--self-test':
        if len(sys.argv) != 3:
            return 2
        return write_self_test_report(sys.argv[2])
    from voice.desktop_instance import already_running, show_existing, release
    try:
        if already_running():
            if not show_existing():
                raise RuntimeError('BARQ is already running. Open it from the notification area beside the Windows clock.')
            return 0
        pending_update = run_desktop()
        if pending_update is not None:
            release()
            pending_update.launch()
        return 0
    except Exception as exc:
        show_startup_error(exc)
        return 1
    finally:
        release()


if __name__ == '__main__':
    sys.exit(main())
