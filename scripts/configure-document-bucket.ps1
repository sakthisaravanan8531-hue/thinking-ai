param([string]$Region='us-east-1',[string]$Origin='https://d3nv2zhw5ihk84.cloudfront.net')
$ErrorActionPreference='Stop'
$bucket='thinkingai-datasourse-bucket'
# Preserve existing CORS rules; add only the admin upload origin.
$previousPreference=$ErrorActionPreference
$ErrorActionPreference='Continue'
try {
 $raw=aws s3api get-bucket-cors --bucket $bucket --region $Region 2>&1
 $corsExit=$LASTEXITCODE
} finally { $ErrorActionPreference=$previousPreference }
if ($corsExit -ne 0) {
 if (($raw | Out-String) -notmatch 'NoSuchCORSConfiguration') { throw "Unable to read document-bucket CORS: $raw" }
 $rules=@()
} else { $rules=@((($raw | Out-String) | ConvertFrom-Json).CORSRules) }
$alreadyConfigured=$false
foreach ($rule in $rules) {
 if ($Origin -in $rule.AllowedOrigins -and 'POST' -in $rule.AllowedMethods -and '*' -in $rule.AllowedHeaders) { $alreadyConfigured=$true }
}
if (!$alreadyConfigured) { $rules+=@{AllowedOrigins=@($Origin);AllowedMethods=@('POST');AllowedHeaders=@('*');MaxAgeSeconds=300} }
$file=Join-Path $env:TEMP ('thinking-ai-cors-'+[guid]::NewGuid().ToString()+'.json')
try {
 [IO.File]::WriteAllText($file,(@{CORSRules=$rules} | ConvertTo-Json -Depth 10),[Text.UTF8Encoding]::new($false))
 aws s3api put-bucket-cors --bucket $bucket --region $Region --cors-configuration "file://$file"
 if ($LASTEXITCODE -ne 0) { throw 'Could not configure admin upload CORS.' }
} finally { Remove-Item $file -ErrorAction SilentlyContinue }
# A Cognito user must never get a public S3 source URL.
aws s3api put-public-access-block --bucket $bucket --region $Region --public-access-block-configuration 'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'
if ($LASTEXITCODE -ne 0) { throw 'Could not secure the document bucket.' }
Write-Host 'Existing document bucket configured for private admin uploads. Existing objects and Bedrock settings were not modified.'
