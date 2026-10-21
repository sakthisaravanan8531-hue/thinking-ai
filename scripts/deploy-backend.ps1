$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location (Join-Path $projectRoot 'aws-backend')
try {
    if (-not (Test-Path '.\samconfig.toml')) { throw 'Copy your existing samconfig.toml here, or review and copy samconfig.example.toml to samconfig.toml.' }
    sam validate --lint --region us-east-1
    if ($LASTEXITCODE -ne 0) { throw 'SAM validation failed.' }
    sam build
    if ($LASTEXITCODE -ne 0) { throw 'SAM build failed.' }
    sam deploy --region us-east-1
    if ($LASTEXITCODE -ne 0) { throw 'SAM deployment did not complete.' }
} finally { Pop-Location }
