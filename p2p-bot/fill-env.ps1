<#
  fill-env.ps1 - asks for every .env value, then uploads .env to the server over SSH.
  Secrets are typed hidden and are never printed or written to this PC's disk.
  DRY_RUN is always written as true.

  Run:  powershell -ExecutionPolicy Bypass -File C:\p2p-bot\fill-env.ps1
#>
param(
    [string]$Server = "78.141.212.182",
    [string]$User = "root",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\id_ed25519_p2pbot",
    [string]$RemoteDir = "/opt/p2p-bot"
)

$ErrorActionPreference = "Stop"

function Show-Help([string]$Title, [string[]]$Lines) {
    Write-Host ""
    Write-Host "== $Title ==" -ForegroundColor Cyan
    foreach ($l in $Lines) { Write-Host "   $l" }
}

function Read-Plain([string]$Title, [string[]]$Help, [string]$Pattern = ".+", [string]$Default = $null, [switch]$Optional) {
    Show-Help $Title $Help
    while ($true) {
        $suffix = if ($Default) { " [Enter = $Default]" } elseif ($Optional) { " [Enter = skip]" } else { "" }
        $v = (Read-Host "   $Title$suffix").Trim()
        if (-not $v -and $Default) { return $Default }
        if (-not $v -and $Optional) { return "" }
        if ($v -match "^(?:$Pattern)$") { return $v }
        Write-Host "   Invalid value, try again." -ForegroundColor Yellow
    }
}

function Read-Secret([string]$Title, [string[]]$Help, [string]$Pattern = "\S+") {
    Show-Help $Title $Help
    while ($true) {
        $secure = Read-Host "   $Title (hidden)" -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $v = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr).Trim() }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
        if ($v -match "^(?:$Pattern)$") { Write-Host "   received ($($v.Length) characters)"; return $v }
        Write-Host "   Empty or invalid, try again." -ForegroundColor Yellow
    }
}

$num = "\d+(\.\d+)?"

# --- preflight ---------------------------------------------------------------------------------------
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) { throw "ssh not found. Install 'OpenSSH Client' from Windows Optional Features." }
if (-not (Test-Path $KeyPath)) { throw "SSH key not found: $KeyPath" }

Write-Host "Checking SSH access to $User@$Server ..."
ssh -i $KeyPath -o BatchMode=yes -o ConnectTimeout=10 "$User@$Server" "test -d $RemoteDir"
if ($LASTEXITCODE -ne 0) { throw "Cannot reach $User@$Server with $KeyPath, or $RemoteDir does not exist on the server." }
Write-Host "SSH OK." -ForegroundColor Green

# --- questions ---------------------------------------------------------------------------------------
$apiKey = Read-Secret "BYBIT_API_KEY" @(
    "The API key from Bybit: profile icon > API > Create New Key > System-generated.",
    "Permissions: P2P trading ONLY. Do NOT enable Withdraw or Transfer.",
    "IP restriction: $Server")
$apiSecret = Read-Secret "BYBIT_API_SECRET" @(
    "The secret Bybit shows once, right after creating the key above.")
$adId = Read-Plain "AD_ID" @(
    "The number of the ad the bot will price. Bybit app: P2P > My Ads > open the ad;",
    "the long number (like 1898988222063644672). The ad must use a FIXED price.") "\d{5,}"
$decimals = Read-Plain "PRICE_DECIMALS" @(
    "How many digits after the dot your currency's price allows. Example: 50.25 -> 2.") "\d" "2"

$tgToken = Read-Secret "TELEGRAM_BOT_TOKEN" @(
    "Telegram: open @BotFather > /newbot > follow the steps. It gives you a token like 123456:ABC...") "\d+:[\w-]+"
$chatId = Read-Plain "TELEGRAM_CHAT_ID" @(
    "Your own Telegram numeric id. Open @userinfobot and press Start; it replies with your Id.",
    "The bot answers ONLY this id. Also press Start on your new bot once so it can message you.") "-?\d+"

$minPrice = Read-Plain "MIN_PRICE" @(
    "Lowest price the bot may ever set (in your currency). Needed before live mode.") $num
do {
    $maxPrice = Read-Plain "MAX_PRICE" @("Highest price the bot may ever set.") $num
    $ok = [decimal]$maxPrice -ge [decimal]$minPrice
    if (-not $ok) { Write-Host "   MAX must be >= MIN ($minPrice)." -ForegroundColor Yellow }
} until ($ok)
$step = Read-Plain "STEP" @("How much better than the best competitor your price will be. Example: 0.01.") $num "0.01"
$minChange = Read-Plain "MIN_CHANGE" @(
    "Skip a price change smaller than this, to save Bybit's edit limit. Example: 0.01.") $num "0.01"
$interval = Read-Plain "INTERVAL_SECONDS" @("How often the bot checks prices, in seconds (15 or more).") "(1[5-9]|[2-9]\d|\d{3,})" "60"
$fRate = Read-Plain "FILTER_MIN_COMPLETION_RATE" @(
    "Ignore competitors whose completion rate (%) is below this. Example: 95.") $num "0"
$fOrders = Read-Plain "FILTER_MIN_ORDERS" @("Ignore competitors with fewer recent orders than this. Example: 50.") "\d+" "0"
$fAmount = Read-Plain "FILTER_MIN_AD_AMOUNT" @(
    "Ignore small ads: competitor's max order limit (in your currency) must be at least this.") $num "0"

# --- build + upload ----------------------------------------------------------------------------------
$lines = @(
    "DRY_RUN=true",
    "EXCHANGE=bybit",
    "BYBIT_API_KEY=$apiKey",
    "BYBIT_API_SECRET=$apiSecret",
    "BYBIT_BASE_URL=",
    "AD_ID=$adId",
    "PRICE_DECIMALS=$decimals",
    "TELEGRAM_BOT_TOKEN=$tgToken",
    "TELEGRAM_CHAT_ID=$chatId",
    "MIN_PRICE=$minPrice",
    "MAX_PRICE=$maxPrice",
    "STEP=$step",
    "MIN_CHANGE=$minChange",
    "INTERVAL_SECONDS=$interval",
    "FILTER_MIN_COMPLETION_RATE=$fRate",
    "FILTER_MIN_ORDERS=$fOrders",
    "FILTER_MIN_AD_AMOUNT=$fAmount"
)
$content = ($lines -join "`n") + "`n"

# Sent through ssh's stdin (not the command line), written atomically with 600 permissions.
$remote = "set -e; umask 077; tmp=$RemoteDir/.env.new; tr -d '\r' > `$tmp; " +
          "if id p2pbot >/dev/null 2>&1; then chown p2pbot:p2pbot `$tmp; fi; " +
          "chmod 600 `$tmp; mv `$tmp $RemoteDir/.env; stat -c 'server .env: mode %a, owner %U, %s bytes' $RemoteDir/.env"

Write-Host ""
Write-Host "Uploading .env to $Server ..."
$prevEnc = $OutputEncoding
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
try {
    $content | ssh -i $KeyPath -o BatchMode=yes "$User@$Server" $remote
    if ($LASTEXITCODE -ne 0) { throw "Upload failed (ssh exit code $LASTEXITCODE)." }
} finally {
    $OutputEncoding = $prevEnc
    $apiKey = $apiSecret = $tgToken = $content = $lines = $null
    [GC]::Collect()
}

Write-Host "Done. DRY_RUN=true (the bot will only report, not change prices)." -ForegroundColor Green
Write-Host "Next: tell Claude 'done', or run check-bot.ps1."
