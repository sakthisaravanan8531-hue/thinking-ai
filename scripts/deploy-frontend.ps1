param([string]$Region='us-east-1')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
& "$PSScriptRoot\configure-site.ps1" -Region $Region
aws s3 sync "$projectRoot\dist" s3://thinking-ai-web-912010732788 --region $Region --cache-control 'no-cache'
if ($LASTEXITCODE -ne 0) { throw 'Frontend upload failed.' }
aws s3 rm s3://thinking-ai-web-912010732788/aws-client.js --region $Region
aws cloudfront create-invalidation --distribution-id E1Q60LVMJ9T8M9 --paths '/*'
if ($LASTEXITCODE -ne 0) { throw 'Invalidation failed.' }
Write-Host 'After invalidation: https://d3nv2zhw5ihk84.cloudfront.net/ — Admin: /admin.html'
