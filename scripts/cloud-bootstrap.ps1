param(
    [Parameter(Mandatory = $true)]
    [string]$PackageUrl,

    [string]$InstallDir = "$env:ProgramFiles\SimpleRemote",
    [string]$PythonExe = "python",
    [string]$Token = "",
    [switch]$NoInteractive = $false
)

$ErrorActionPreference = "Stop"

$tempDir = Join-Path $env:TEMP ("simple_remote_cloud_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

try {
  $zipPath = Join-Path $tempDir "simple-remote-package.zip"
  Write-Host "[1/5] Baixando pacote..."
  Invoke-WebRequest -Uri $PackageUrl -UseBasicParsing -OutFile $zipPath

  Write-Host "[2/5] Extraindo pacote..."
  $extractDir = Join-Path $tempDir "payload"
  New-Item -ItemType Directory -Path $extractDir -Force | Out-Null
  Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

  $pkgRoot = $extractDir
  if (-not (Test-Path (Join-Path $pkgRoot "scripts/install.ps1"))) {
    $candidates = Get-ChildItem -Path $extractDir -Recurse -Filter "install.ps1" | Where-Object { $_.FullName -match "scripts[\\/]install\.ps1$" }
    if ($candidates.Count -gt 0) {
      $pkgRoot = $candidates[0].Directory.Parent.FullName
    } else {
      throw "Não foi encontrado install.ps1 dentro do pacote."
    }
  }

  Write-Host "[3/5] Executando instalação local..."
  & (Join-Path $pkgRoot "scripts\install.ps1") -InstallDir $InstallDir -PythonExe $PythonExe -Token $Token -NoInteractive:$NoInteractive

  Write-Host "[4/5] Finalizando..."
  Write-Host "Instalação concluída."
  Write-Host "Atalhos criados em: $([Environment]::GetFolderPath("Desktop"))"
} finally {
  Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}