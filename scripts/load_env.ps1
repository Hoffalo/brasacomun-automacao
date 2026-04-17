# Uso: na raiz do projeto, rode:
#   . .\scripts\load_env.ps1
# (com o ponto e espaço antes do caminho — senão as env vars não ficam na sessão)
#
# Requer:
#   secrets/.env.local    → formato KEY=VALUE, uma var por linha
#   secrets/*.json        → Service Account JSON (carregado direto no env)

$envFile = "secrets/.env.local"

if (-not (Test-Path $envFile)) {
    Write-Host "Arquivo $envFile não existe." -ForegroundColor Yellow
    Write-Host "Crie com o formato:"
    Write-Host "  CLICKUP_API_TOKEN=pk_..."
    Write-Host "  ANTHROPIC_API_KEY=sk-ant-..."
    Write-Host "  ... (veja README)"
    return
}

# 1. Carrega variáveis simples do .env.local
$loaded = 0
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) { return }
    if ($line -match "^([A-Z_][A-Z0-9_]*)=(.*)$") {
        $key = $matches[1]
        $val = $matches[2].Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($key, $val, "Process")
        $loaded++
    }
}

# 2. Carrega Service Account JSON direto do arquivo (se existir)
$saJson = Get-ChildItem -Path "secrets/" -Filter "*service*.json" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $saJson) {
    $saJson = Get-ChildItem -Path "secrets/" -Filter "automacao-clickup-*.json" -ErrorAction SilentlyContinue | Select-Object -First 1
}
if ($saJson) {
    $env:GOOGLE_SERVICE_ACCOUNT_JSON = Get-Content $saJson.FullName -Raw
    $loaded++
    Write-Host "  set GOOGLE_SERVICE_ACCOUNT_JSON (from $($saJson.Name))"
}

Write-Host "$loaded env vars carregadas." -ForegroundColor Green
