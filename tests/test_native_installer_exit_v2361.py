from pathlib import Path
import shutil,subprocess
import pytest
ROOT=Path(__file__).resolve().parents[1]

def runtime():
    found=shutil.which('powershell.exe') or shutil.which('pwsh')
    if not found and Path('/tmp/barq-pwsh/pwsh').is_file():found='/tmp/barq-pwsh/pwsh'
    if not found:pytest.skip('PowerShell runtime unavailable')
    return found

@pytest.mark.parametrize('script,marker',[
 ('test_native_installer.ps1','native installer checks passed: 10'),
 ('test_inno_discovery.ps1','Inno discovery checks passed: 3'),
 ('test_inno_functional_probe.ps1','Inno functional checks passed: 9'),
])
def test_actual_process_exit_and_compatible_discovery(script,marker):
    result=subprocess.run([runtime(),'-NoProfile','-NonInteractive','-File',str(ROOT/'scripts'/script)],cwd=ROOT,capture_output=True,text=True,timeout=55)
    assert result.returncode==0,result.stdout+result.stderr
    assert marker in result.stdout

def test_installer_runner_no_longer_reads_redirected_start_process_exitcode():
    source=(ROOT/'scripts/build_prerequisites.ps1').read_text()
    body=source.split('function Invoke-BarqInstaller(',1)[1].split('function Wait-BarqBuildTool(',1)[0]
    assert 'Start-Process' not in body and '$process.ExitCode' not in body
    assert '$null -eq $result.ExitCode' in body
    assert 'new ProcessStartInfo(file, args)' in source
    assert 'process.StartInfo.UseShellExecute = false' in source
    assert source.index('var output = Task.Run')<source.index('process.WaitForExit(timeoutMs)')
    assert 'Wait-BarqBuildTool $package.Probe' in source
