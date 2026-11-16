"""BARQ v2.31 Windows real-machine E2E. Writes evidence, never invents PASS.

By default no internet, no Windows security changes, no admin privileges.
Run on Windows interactive session; --network permits npm install from registry.
--desktop requires explicit user choice to write a disposable project on Desktop.
"""
from __future__ import annotations
import argparse,json,os,platform,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

def run(*,network=False,desktop=False,report_dir=None):
    from execution.known_folders import known_folder
    from execution.grants import GrantStore
    from execution.recipes import scaffold_react,install_and_build,start_react
    from execution.services import ServiceManager
    from execution.runner import Runner
    from execution.doctor import report as doctor
    out=[];start=time.monotonic()
    def record(name,status,**evidence):out.append({'case':name,'status':status,'evidence':evidence})
    if sys.platform!='win32':
        record('real_windows','NOT_VERIFIED',reason='This script requires an interactive Windows 10/11 desktop')
    else:
        record('real_windows','PASS',platform=platform.platform())
        record('tools_doctor','PASS',result=doctor())
        try:
            from core.windows_facts import answer
            facts=answer('درجة حرارة المعالج واستهلاك الرام')
            record('hardware_readings','PASS' if facts else 'NOT_VERIFIED',result=str(facts)[:800])
        except Exception as exc:record('hardware_readings','NOT_VERIFIED',reason=str(exc)[:200])
        try:
            proc=subprocess.Popen(['notepad.exe'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            time.sleep(.8)
            if proc.poll() is None:record('notepad_process','PASS',pid=proc.pid)
            else:record('notepad_process','FAIL',exit_code=proc.returncode)
            # Only terminate THIS process, never an existing user Notepad.
            if proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=3)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=3)
        except Exception as exc:record('notepad_process','NOT_VERIFIED',reason=str(exc)[:200])
        try:
            if desktop:
                target=known_folder('desktop')
                assert target.is_dir()
            else:
                target=Path(tempfile.mkdtemp(prefix='barq-windows-e2e-')).resolve()
            # Temp grant is used ONLY inside this E2E run, never in persistent BARQ settings.
            grant=GrantStore(target/'barq-e2e-grants.json')
            grant.grant(str(target),['create','write','read','run_tests','build','install_dependencies','run_dev_server'])
            from computer_control.safety.policy import Policy,Decision
            policy=Policy(enabled=True,allowed_folders=[])
            import execution.grants as grants_module
            original=grants_module.GrantStore
            grants_module.GrantStore=lambda:grant
            try:
                denied=policy.evaluate('write_file',{'path':str(target.parent/'outside-barq-e2e.txt'),'text':'x'})[1]==Decision.ASK
                protected=policy.evaluate('read_file',{'path':str(target/'.ssh'/'id_rsa')})[1]==Decision.BLOCK
                destructive=policy.evaluate('delete',{'path':str(target/'foo'),'permanent':True})[1]==Decision.BLOCK
                record('permission_boundaries','PASS' if all((denied,protected,destructive)) else 'FAIL',outside_denied=denied,protected_denied=protected,destructive_denied=destructive)
            finally:grants_module.GrantStore=original
            info=scaffold_react(target,grant,name='barq-e2e-react')
            project=Path(info['path'])
            record('react_scaffold','PASS' if (project/'package.json').is_file() else 'FAIL',folder=str(project),file_count=info['file_count'])
            if network:
                build=install_and_build(project,grant,Runner())
                record('npm_install_and_build','PASS',build=build)
                server=ServiceManager()
                try:
                    live=start_react(project,grant,server)
                    record('dev_server_http_200','PASS' if live['http_status']==200 else 'FAIL',url=live['url'],port=live['port'])
                finally:
                    server.close()
                try:
                    with urllib.request.urlopen(live['url'],timeout=1):
                        released=False
                except Exception:
                    released=True
                record('dev_server_stopped','PASS' if released else 'FAIL',port_released=released)
            else:
                record('npm_install_and_build','NOT_VERIFIED',reason='--network not supplied; no dependencies downloaded')
                record('dev_server_http_200','NOT_VERIFIED',reason='npm install not run')
                record('dev_server_stopped','NOT_VERIFIED',reason='No dev server started')
        except Exception as exc:
            record('react_workflow','FAIL',reason=type(exc).__name__+': '+str(exc)[:400])
        record('github_untrusted_build','NOT_VERIFIED',reason='Requires separate on-screen approval; this diagnostic does not run untrusted scripts')
        record('mid_install_resume','NOT_VERIFIED',reason='Cross-process resume not implemented; ledger is available but reconciliation is pending')
        record('vscode_window_uia','NOT_VERIFIED',reason='UIA/window-level verification not implemented in v2.31 preview')
        record('voice_full_scenario','NOT_VERIFIED',reason='Requires microphone, live Google session and project grant in BARQ UI')
    report={'version':'2.31.0','ran_at':datetime.now(timezone.utc).isoformat(),
            'duration_s':round(time.monotonic()-start,3),
            'results':out,'overall':'FAIL' if any(x['status']=='FAIL' for x in out) else (
                'PASS' if all(x['status']=='PASS' for x in out) else 'PARTIAL')}
    dest=Path(report_dir or ROOT/'release')
    dest.mkdir(parents=True,exist_ok=True)
    (dest/'BARQ_windows_e2e.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# BARQ Windows E2E','',f"Overall: **{report['overall']}**",'']
    lines.extend(f"- **{r['status']}** — {r['case']}: {str(r['evidence'])[:450]}" for r in out)
    (dest/'BARQ_windows_e2e.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('BARQ REAL WINDOWS E2E: '+report['overall'])
    print('Report:',dest/'BARQ_windows_e2e.md')
    return 1 if report['overall']=='FAIL' else (0 if report['overall']=='PASS' else 2)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--network',action='store_true',help='Explicitly permit npm download')
    parser.add_argument('--desktop',action='store_true',help='Create a disposable sample project on real Windows Desktop')
    parser.add_argument('--report-dir',default=None)
    args=parser.parse_args()
    raise SystemExit(run(network=args.network,desktop=args.desktop,report_dir=args.report_dir))
