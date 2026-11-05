param([string]$Region='us-east-1',[string]$StackName='thinking-ai-backend',[switch]$EnableFallback)
$ErrorActionPreference='Stop'
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw 'AWS/SAM command failed. Deployment stopped.' } }
$projectRoot=Split-Path $PSScriptRoot -Parent
$account=aws sts get-caller-identity --query Account --output text; Check-Exit
if ($account -ne '912010732788') { throw "Wrong AWS account: $account" }
$knowledge=aws cloudformation describe-stacks --stack-name thinking-ai-knowledge --region $Region --output json | ConvertFrom-Json; Check-Exit
if ($knowledge.Stacks[0].StackStatus -notin @('CREATE_COMPLETE','UPDATE_COMPLETE')) { throw 'The knowledge stack must finish successfully first.' }
$current=aws cloudformation describe-stacks --stack-name $StackName --region $Region --output json | ConvertFrom-Json; Check-Exit
$allowed=@('PrimaryProvider','SiteOrigin','CloudFrontOrigin','OutputTokenLimit','BedrockModelId','GeminiModelId','GeminiKeyParameter','GlobalDailyLimit','UserDailyLimit','AppEnabled','DocumentFallbackEnabled','IndexDailyLimit')
$overrides=@()
foreach ($parameter in $current.Stacks[0].Parameters) {
 if ($parameter.ParameterKey -in $allowed) { $overrides += "$($parameter.ParameterKey)=$($parameter.ParameterValue)" }
}
if ($EnableFallback) {
 $overrides=@($overrides | Where-Object { $_ -notlike 'PrimaryProvider=*' -and $_ -notlike 'DocumentFallbackEnabled=*' })
 $overrides+='PrimaryProvider=bedrock'
 $overrides+='DocumentFallbackEnabled=true'
}
foreach ($output in $knowledge.Stacks[0].Outputs) { $overrides += "$($output.OutputKey)=$($output.OutputValue)" }
& "$PSScriptRoot\configure-document-bucket.ps1" -Region $Region
Set-Location "$projectRoot\aws-backend"
$configPath=Join-Path $env:TEMP 'thinking-ai-professional-sam.toml'
[IO.File]::WriteAllText($configPath,'version = 0.1',[Text.UTF8Encoding]::new($false))
sam validate --lint --region $Region; Check-Exit
sam build; Check-Exit
sam deploy --config-file $configPath --stack-name $StackName --region $Region --resolve-s3 --capabilities CAPABILITY_IAM --parameter-overrides $overrides --confirm-changeset --no-disable-rollback; Check-Exit
& "$PSScriptRoot\configure-site.ps1" -Region $Region -StackName $StackName
