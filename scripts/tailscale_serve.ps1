# Shares http://127.0.0.1:<port> privately on your tailnet over HTTPS with `tailscale serve`.
param([int]$Port = 0)

$root = Split-Path -Parent $PSScriptRoot
if ($Port -eq 0) {
    $Port = 8765
    $cfg = Join-Path $root "config.json"
    if (Test-Path $cfg) { try { $Port = (Get-Content $cfg -Raw | ConvertFrom-Json).port } catch {} }
}

$ts = (Get-Command tailscale -ErrorAction SilentlyContinue).Source
if (-not $ts -and (Test-Path "C:\Program Files\Tailscale\tailscale.exe")) { $ts = "C:\Program Files\Tailscale\tailscale.exe" }

Write-Host ""
Write-Host "--- Phone access with Tailscale (free) ---"
if (-not $ts) {
    Write-Host "Tailscale is not installed yet. To finish:"
    Write-Host " 1. Install Tailscale on this PC: https://tailscale.com/download and sign in."
    Write-Host " 2. In https://login.tailscale.com/admin/dns turn on MagicDNS and HTTPS Certificates."
    Write-Host " 3. Run setup.bat again (or: tailscale serve --bg $Port)."
    Write-Host " 4. Install Tailscale on your phone and sign in with the same account."
    exit 0
}

& $ts serve --bg $Port
if ($LASTEXITCODE -ne 0) {
    Write-Host "tailscale serve failed. Make sure you're signed in, and that MagicDNS + HTTPS"
    Write-Host "Certificates are enabled at https://login.tailscale.com/admin/dns, then run:"
    Write-Host "   tailscale serve --bg $Port"
    exit 0
}
try {
    $dns = ((& $ts status --json) | ConvertFrom-Json).Self.DNSName.TrimEnd(".")
    Write-Host "Open this on your phone (with Tailscale on):  https://$dns"
} catch {
    Write-Host "Run 'tailscale serve status' to see your https://....ts.net address."
}
