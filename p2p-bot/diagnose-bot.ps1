<#
  diagnose-bot.ps1 - shows why the service is not staying active, without revealing secrets.
  Prints the service state, file ownership, and the latest journal lines with the Bybit key/secret
  and Telegram token replaced by *** (they are read on the server and never printed).

  Run:  powershell -ExecutionPolicy Bypass -File C:\p2p-bot\diagnose-bot.ps1
#>
param(
    [string]$Server = "78.141.212.182",
    [string]$User = "root",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\id_ed25519_p2pbot",
    [string]$RemoteDir = "/opt/p2p-bot"
)

$ErrorActionPreference = "Stop"
$remote = @'
cd __DIR__
echo '--- service'
systemctl show p2p-bot -p ActiveState -p SubState -p Result -p ExecMainStatus -p NRestarts
echo '--- ownership (should all be p2pbot)'
stat -c '%U:%G %a %n' . .env data logs logs/* data/* 2>/dev/null
echo '--- last 120 journal lines (secrets masked)'
journalctl -u p2p-bot -n 120 --no-pager -o short-iso | python3 -c '
import sys
secrets = []
for line in open(".env", encoding="utf-8"):
    k, _, v = line.strip().partition("=")
    if k in ("BYBIT_API_KEY", "BYBIT_API_SECRET", "TELEGRAM_BOT_TOKEN") and len(v) >= 6:
        secrets.append(v)
for line in sys.stdin:
    for s in secrets:
        line = line.replace(s, "***")
    sys.stdout.write(line)
'
'@ -replace "__DIR__", $RemoteDir -replace "`r", ""

$prevEnc = $OutputEncoding
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
try { $remote | ssh -i $KeyPath -o BatchMode=yes "$User@$Server" "tr -d '\r' | bash -s" }
finally { $OutputEncoding = $prevEnc }
