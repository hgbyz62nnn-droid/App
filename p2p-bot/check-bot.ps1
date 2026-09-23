<#
  check-bot.ps1 - restarts the service, scans recent logs for errors, and runs the connectivity
  self-test (Bybit + Telegram, sends you a test message). Never prints .env.

  Run:  powershell -ExecutionPolicy Bypass -File C:\p2p-bot\check-bot.ps1
#>
param(
    [string]$Server = "78.141.212.182",
    [string]$User = "root",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\id_ed25519_p2pbot",
    [string]$RemoteDir = "/opt/p2p-bot"
)

$ErrorActionPreference = "Stop"
$remote = @"
set -u
start="`$(date '+%Y-%m-%d %H:%M:%S')"
echo '--- restart'
systemctl restart p2p-bot && sleep 20  # long enough to catch a crash + auto-restart (RestartSec=10)
echo "service: `$(systemctl is-active p2p-bot)"
echo '--- warnings/errors since restart'
journalctl -u p2p-bot --since "`$start" --no-pager -o cat | grep -E 'WARNING|ERROR|CRITICAL|Traceback|Missing required' || echo '(none)'
echo '--- self-test'
cd $RemoteDir && sudo -u p2pbot $RemoteDir/.venv/bin/python -m p2pbot.selftest
"@ -replace "`r", ""

# Script goes through stdin: Windows PowerShell 5.1 mangles double quotes in native-command arguments.
$prevEnc = $OutputEncoding
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
try { $remote | ssh -i $KeyPath -o BatchMode=yes "$User@$Server" "tr -d '\r' | bash -s" }
finally { $OutputEncoding = $prevEnc }
if ($LASTEXITCODE -eq 0) { Write-Host "All checks passed. Check Telegram for the test message." -ForegroundColor Green }
else { Write-Host "Some checks failed - see the FAIL lines above." -ForegroundColor Yellow }
