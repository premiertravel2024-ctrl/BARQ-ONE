# Read-only diagnostics; no API key, account data, or Windows settings are changed.
$ErrorActionPreference = 'Continue'
$target = 'generativelanguage.googleapis.com'
Write-Host 'BARQ Gemini Live - Windows network diagnostics' -ForegroundColor Cyan
Write-Host "Target: $target (HTTPS/WSS port 443)"
Write-Host ''
try {
    $ip = @(Resolve-DnsName $target -ErrorAction Stop | Where-Object { $_.Type -in @('A','AAAA') } | Select-Object -ExpandProperty IPAddress)
    if (-not $ip -or $ip.Count -lt 1) { throw 'DNS did not return a usable address.' }
    Write-Host 'DNS lookup: OK' -ForegroundColor Green
    Write-Host ("Resolved address count: {0}" -f $ip.Count)
} catch {
    Write-Host 'DNS lookup: FAILED' -ForegroundColor Red
    Write-Host 'Windows could not resolve the Google Gemini API hostname.'
    Write-Host 'Check internet access, DNS filtering, proxy or VPN; retry after fixing DNS.'
    Write-Host 'No Gemini account quota/key conclusion can be drawn from this error.'
    exit 2
}
try {
    $connected = Test-NetConnection -ComputerName $target -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue -ErrorAction Stop
    if ($connected) {
        Write-Host 'TCP port 443: reachable' -ForegroundColor Green
        Write-Host 'DNS/TCP basic connectivity works. If Live still fails, inspect the BARQ error message.'
        exit 0
    }
} catch { }
Write-Host 'TCP port 443: could not connect' -ForegroundColor Red
Write-Host 'A firewall, corporate proxy, VPN or network restriction may block the connection.'
exit 3
