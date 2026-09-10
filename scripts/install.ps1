param(
    [string]$InstallDir = "$env:ProgramFiles\SimpleRemote",
    [string]$PythonExe = "python",
    [string]$Token = "",
    [switch]$NoInteractive = $false
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $root ".."

Write-Host "[1/6] Preparando pasta..."
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

$items = @(
  "host.py",
  "README.md",
  "requirements.txt",
  "viewer",
  "scripts"
)
foreach ($item in $items) {
  $srcPath = Join-Path $source $item
  if (Test-Path $srcPath) {
    Copy-Item -Path $srcPath -Destination $InstallDir -Recurse -Force
  }
}

Write-Host "[2/6] Definindo token de controle..."
if ([string]::IsNullOrWhiteSpace($Token)) {
  if (-not $NoInteractive) {
    $Token = Read-Host -Prompt "Token de controle (deixe vazio para gerar automático)"
  }
  if ([string]::IsNullOrWhiteSpace($Token)) {
    $bytes = New-Object byte[] 18
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $Token = [Convert]::ToBase64String($bytes).Replace("+","-").Replace("/","_").Substring(0,24)
  }
}
Set-Content -Path (Join-Path $InstallDir ".remote_token") -Value $Token -Encoding utf8

Write-Host "[3/6] Criando ambiente virtual..."
$venvDir = Join-Path $InstallDir ".venv"
& $PythonExe -m venv $venvDir

Write-Host "[4/6] Instalando dependencias..."
& (Join-Path $venvDir "Scripts\pip.exe") install -r (Join-Path $InstallDir "requirements.txt")

Write-Host "[5/6] Gerando atalhos..."
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath("Desktop")

$hostShortcut = $shell.CreateShortcut((Join-Path $desktop "SimpleRemote - Host.lnk"))
$hostShortcut.TargetPath = (Join-Path $InstallDir "scripts\start-host-pairing.bat")
$hostShortcut.WorkingDirectory = $InstallDir
$hostShortcut.IconLocation = "shell32.dll,19"
$hostShortcut.Save()

$viewerShortcut = $shell.CreateShortcut((Join-Path $desktop "SimpleRemote - Viewer.lnk"))
$viewerShortcut.TargetPath = (Join-Path $InstallDir "scripts\start-viewer.bat")
$viewerShortcut.WorkingDirectory = $InstallDir
$viewerShortcut.Save()

Write-Host "[6/6] Pronto."
Write-Host "Atalho Host criado em: $desktop\SimpleRemote - Host.lnk"
Write-Host "Atalho Viewer criado em: $desktop\SimpleRemote - Viewer.lnk"
Write-Host "Token salvo em: $InstallDir\.remote_token"