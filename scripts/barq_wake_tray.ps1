# Explicit opt-in wake listener. Local microphone only; no recordings or uploads.
# Windows PowerShell 5.1, System.Speech and installed Windows speech recognizer.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Speech
# Stop duplicate listeners from fighting for the same microphone.
$createdNew=$false
$singleInstance=[System.Threading.Mutex]::new($true,'Local\BARQ-Wake-Listener',[ref]$createdNew)
if(-not $createdNew){exit 0}
$script:discoveryFile = Join-Path $env:LOCALAPPDATA 'AI Router Agent\wake_endpoint.json'
$script:paused = $false
$script:quit = $false
$script:queue = New-Object 'System.Collections.Concurrent.ConcurrentQueue[string]'
$script:listening = $false
$script:resumeAt = [DateTime]::MinValue

$tray = New-Object System.Windows.Forms.NotifyIcon
$tray.Icon = [System.Drawing.SystemIcons]::Application
$tray.Visible = $true
$tray.Text = 'BARQ wake listener'
$menu = New-Object System.Windows.Forms.ContextMenuStrip
$pauseItem = $menu.Items.Add('إيقاف الميكروفون مؤقتاً')
$quitItem = $menu.Items.Add('إغلاق مساعد الخلفية')
$tray.ContextMenuStrip = $menu
$pauseItem.add_Click({ $script:paused = -not $script:paused; $pauseItem.Text = if($script:paused){'استئناف الميكروفون'}else{'إيقاف الميكروفون مؤقتاً'} })
$quitItem.add_Click({ $script:quit = $true })

function Notify([string]$text) {
  $tray.BalloonTipTitle = 'BARQ'
  $tray.BalloonTipText = $text
  $tray.ShowBalloonTip(3000)
}
function Endpoint {
  if(-not (Test-Path -LiteralPath $script:discoveryFile -PathType Leaf)){return $null}
  try {
    $endpoint = Get-Content -LiteralPath $script:discoveryFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if(([int]$endpoint.port -lt 1) -or ([int]$endpoint.port -gt 65535) -or (-not $endpoint.token)){return $null}
    return $endpoint
  } catch {return $null}
}
function LiveActive($endpoint) {
  if(-not $endpoint){return $false}
  try {
    $response = Invoke-RestMethod -Method GET -Uri ("http://127.0.0.1:{0}/v1/voice/wake/session" -f $endpoint.port) -TimeoutSec 2
    return [bool]$response.live_active
  } catch {return $false}
}
function Trigger([string]$phrase) {
  $endpoint=Endpoint
  $alive = $false
  if($endpoint){try {$null=Invoke-RestMethod -Method GET -Uri ("http://127.0.0.1:{0}/v1/voice/wake/session" -f $endpoint.port) -TimeoutSec 2; $alive=$true}catch{}}
  if(-not $alive){
    $exe=Join-Path (Split-Path $PSScriptRoot -Parent) 'BARQ.exe'
    if(-not (Test-Path -LiteralPath $exe -PathType Leaf)){Notify 'شغّل برق الأول، وبعدها نادي يا برق.';return $false}
    try {Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe -Parent) | Out-Null}catch{return $false}
    for($n=0;$n -lt 45;$n++){
      Start-Sleep -Milliseconds 300
      $endpoint=Endpoint
      if($endpoint){try{$null=Invoke-RestMethod -Method GET -Uri ("http://127.0.0.1:{0}/v1/voice/wake/session" -f $endpoint.port) -TimeoutSec 2; $alive=$true;break}catch{}}
    }
  }
  if(-not $alive){Notify 'تعذّر تشغيل برق. افتحه يدويًا للتحقق.';return $false}
  try {
    $payload = @{phrase=$phrase} | ConvertTo-Json -Compress
    $headers = @{'X-BARQ-WAKE-TOKEN'=[string]$endpoint.token}
    $result = Invoke-RestMethod -Method POST -Uri ("http://127.0.0.1:{0}/v1/voice/wake/trigger" -f $endpoint.port) -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($payload)) -TimeoutSec 3
    if($result.queued){
      try {(New-Object -ComObject WScript.Shell).AppActivate('BARQ') | Out-Null} catch {}
      Notify 'سامعك، بفتح مكالمة برق. اتكلم بطبيعتك.'
      return $true
    }
  } catch {Notify 'مش قادر أوصل لبرق. افتح البرنامج وحاول تاني.'}
  return $false
}
$recognizer=$null
try {
  $installed = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()
  $chosen = $installed | Where-Object { $_.Culture.Name -match '^ar(-|$)' } | Select-Object -First 1
  if(-not $chosen){
    $chosen = $installed | Where-Object { $_.Culture.Name -match '^en(-|$)' } | Select-Object -First 1
    if(-not $chosen){throw 'No installed Windows speech recognizer for Arabic or English.'}
    Notify 'التعرف على العربي مش مثبت. قول Hey Barq مؤقتاً أو ثبّت التعرف الصوتي العربي.'
  }
  $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine -ArgumentList @($chosen)
  $choices = New-Object System.Speech.Recognition.Choices
  $phrases = if($chosen.Culture.Name -match '^ar'){@('يا برق','برق')}else{@('hey barq','barq','hey bark')}
  foreach($phrase in $phrases){$choices.Add([string]$phrase)}
  $grammarBuilder = New-Object System.Speech.Recognition.GrammarBuilder
  $grammarBuilder.Culture=$chosen.Culture
  $grammarBuilder.Append($choices)
  $grammar=New-Object System.Speech.Recognition.Grammar -ArgumentList @($grammarBuilder)
  $recognizer.LoadGrammar($grammar)
  $recognizer.SetInputToDefaultAudioDevice()
  $eventRegistration=Register-ObjectEvent -InputObject $recognizer -EventName SpeechRecognized -SourceIdentifier 'BARQ_WAKE_WORD' -MessageData $script:queue -Action {
    $recognized=$Event.SourceEventArgs.Result
    if($recognized -and $recognized.Confidence -ge 0.58){$Event.MessageData.Enqueue([string]$recognized.Text)}
  }
  Notify 'مساعد الخلفية اشتغل. قول يا برق، أو اضغط يمين لإيقاف الميكروفون.'
  while(-not $script:quit){
    [System.Windows.Forms.Application]::DoEvents()
    $endpoint=Endpoint
    $busy=(LiveActive $endpoint) -or ([DateTime]::UtcNow -lt $script:resumeAt)
    $allowed= -not $script:paused -and -not $busy
    if($allowed -and -not $script:listening){
      try {
        $recognizer.RecognizeAsync([System.Speech.Recognition.RecognizeMode]::Multiple)
        $script:listening=$true
      } catch [System.InvalidOperationException] { Start-Sleep -Milliseconds 200 }
    } elseif(-not $allowed -and $script:listening){
      $recognizer.RecognizeAsyncCancel()
      $script:listening=$false
    }
    $phrase=$null
    if($script:queue.TryDequeue([ref]$phrase) -and -not $script:paused){
      if($script:listening){$recognizer.RecognizeAsyncCancel();$script:listening=$false}
      if(Trigger $phrase){$script:resumeAt=[DateTime]::UtcNow.AddSeconds(20)}
      else{$script:resumeAt=[DateTime]::UtcNow.AddSeconds(3)}
    }
    $tray.Text=if($script:paused){'BARQ mic paused'}elseif($busy){'BARQ voice call active'}else{'BARQ listening for wake word'}
    Start-Sleep -Milliseconds 350
  }
} catch {
  [System.Windows.Forms.MessageBox]::Show("BARQ wake failed: $($_.Exception.Message)`nInstall a Windows speech recognition language pack.",'BARQ wake listener') | Out-Null
} finally {
  if($recognizer){try{$recognizer.RecognizeAsyncCancel()}catch{};$recognizer.Dispose()}
  Unregister-Event -SourceIdentifier 'BARQ_WAKE_WORD' -ErrorAction SilentlyContinue
  $tray.Visible=$false
  $tray.Dispose()
  try{$singleInstance.ReleaseMutex()}catch{}
  $singleInstance.Dispose()
}
