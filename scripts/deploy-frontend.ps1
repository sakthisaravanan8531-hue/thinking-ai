param(
    [string]$BucketName = 'thinking-ai-web-912010732788',
    [string]$DistributionId = 'E1Q60LVMJ9T8M9'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$frontendPath = Join-Path $projectRoot 'dist'
if (-not (Test-Path (Join-Path $frontendPath 'index.html'))) { throw 'Frontend files missing.' }
aws s3 sync $frontendPath "s3://$BucketName" --region us-east-1 --cache-control 'no-cache'
if ($LASTEXITCODE -ne 0) { throw 'S3 upload failed.' }
aws cloudfront create-invalidation --distribution-id $DistributionId --paths '/*'
if ($LASTEXITCODE -ne 0) { throw 'CloudFront invalidation failed.' }
Write-Output 'Frontend uploaded. Refresh after CloudFront invalidation completes.'
