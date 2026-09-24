<#
  deploy-capture.ps1 - step A: deploys the notification capture webhook.
    * uploads the code from C:\p2p-bot
    * creates WEBHOOK_TOKEN in the server's .env if missing (never prints .env)
    * installs Caddy (HTTPS on 443 only), the p2p-capture service, and opens 443 in ufw
    * runs an end-to-end test through HTTPS and checks the capture file
    * prints the webhook URL and token ONCE for MacroDroid

  Run:  powershell -ExecutionPolicy Bypass -File C:\p2p-bot\deploy-capture.ps1
#>
param(
    [string]$Domain = "nafe3p2p.duckdns.org",
    [string]$Server = "78.141.212.182",
    [string]$User = "root",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\id_ed25519_p2pbot",
    [string]$LocalDir = "C:\p2p-bot",
    [string]$RemoteDir = "/opt/p2p-bot"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path "$LocalDir\p2pbot\capture.py")) { throw "$LocalDir\p2pbot\capture.py not found - update C:\p2p-bot from the repo first." }

Write-Host "Uploading code ..."
foreach ($item in "p2pbot", "deploy", "tests", "requirements.txt", "requirements-dev.txt") {
    scp -q -r -i $KeyPath "$LocalDir\$item" "${User}@${Server}:$RemoteDir/"
    if ($LASTEXITCODE -ne 0) { throw "Upload of $item failed." }
}

$remote = @'
set -euo pipefail
DOMAIN='__DOMAIN__'
cd __DIR__
export DEBIAN_FRONTEND=noninteractive

echo '--- token'
if ! grep -qE '^WEBHOOK_TOKEN=[0-9a-f]{32,}$' .env; then
  sed -i '/^WEBHOOK_TOKEN=/d' .env
  printf 'WEBHOOK_TOKEN=%s\n' "$(openssl rand -hex 32)" >> .env
  echo 'created a new WEBHOOK_TOKEN'
else
  echo 'keeping the existing WEBHOOK_TOKEN'
fi
chown -R p2pbot:p2pbot __DIR__ && chmod 600 .env
TOKEN=$(grep -E '^WEBHOOK_TOKEN=' .env | cut -d= -f2-)

echo '--- tests'
.venv/bin/pip install -q pytest >/dev/null
sudo -u p2pbot .venv/bin/python -m pytest -q -p no:cacheprovider tests 2>&1 | tail -1

echo '--- caddy'
if ! command -v caddy >/dev/null; then
  apt-get install -y -q debian-keyring debian-archive-keyring apt-transport-https curl gpg >/dev/null
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q >/dev/null && apt-get install -y -q caddy >/dev/null
fi
caddy version
sed "s/__DOMAIN__/$DOMAIN/" deploy/Caddyfile > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile 2>&1 | tail -1

echo '--- services'
cp deploy/p2p-capture.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable -q --now p2p-capture caddy
systemctl restart p2p-capture caddy

echo '--- firewall'
ufw allow OpenSSH >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
ufw status | grep -E 'Status|443|22|OpenSSH'

echo '--- end-to-end test over HTTPS (certificate can take ~1 min the first time)'
code=000
for i in $(seq 1 24); do
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "https://$DOMAIN/hook/notify" \
    -H @<(printf 'X-Webhook-Token: %s\n' "$TOKEN") --data-urlencode app=deploy-test \
    --data-urlencode 'text=deploy check' --data-urlencode test=1 || true)
  [ "$code" = 200 ] && break
  sleep 5
done
echo "with token:    HTTP $code (want 200)"
echo "without token: HTTP $(curl -s -o /dev/null -w '%{http_code}' -X POST "https://$DOMAIN/hook/notify" -d app=x || true) (want 401)"
echo "other path:    HTTP $(curl -s -o /dev/null -w '%{http_code}' "https://$DOMAIN/" || true) (want 404)"
tail -n 1 data/notifications.jsonl 2>/dev/null | grep -q '"deploy-test"' && echo 'capture file:  test entry saved' || echo 'capture file:  test entry NOT found'
echo "p2p-capture: $(systemctl is-active p2p-capture)   caddy: $(systemctl is-active caddy)   p2p-bot: $(systemctl is-active p2p-bot)"
[ "$code" = 200 ] || { echo 'HTTPS test failed - recent caddy log:'; journalctl -u caddy -n 15 --no-pager -o cat | cut -c1-220; exit 1; }

echo ''
echo '=== For MacroDroid (shown once; keep it private) ==='
echo "URL:    https://$DOMAIN/hook/notify"
echo "Header: X-Webhook-Token"
echo "Token:  $TOKEN"
'@ -replace "__DIR__", $RemoteDir -replace "__DOMAIN__", $Domain -replace "`r", ""

$prevEnc = $OutputEncoding
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
try { $remote | ssh -i $KeyPath -o BatchMode=yes "$User@$Server" "tr -d '\r' | bash -s" }
finally { $OutputEncoding = $prevEnc }
if ($LASTEXITCODE -eq 0) { Write-Host "`nStep A deployed. Set up MacroDroid next." -ForegroundColor Green }
else { Write-Host "`nSomething failed - send Claude the output above." -ForegroundColor Yellow }
