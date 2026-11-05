param([string]$Region='us-east-1',[string]$StackName='thinking-ai-backend')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$raw=aws cloudformation describe-stacks --stack-name $StackName --region $Region --query 'Stacks[0].Outputs' --output json
if ($LASTEXITCODE -ne 0) { throw 'Could not read stack outputs.' }
$values=@{}; foreach ($item in ($raw | ConvertFrom-Json)) { $values[$item.OutputKey]=$item.OutputValue }
if (!$values.AdminClientId) { throw 'Deploy the professional backend first.' }
$config=@{apiUrl=$values.ApiUrl;region=$Region;staffClientId=$values.ClientId;adminClientId=$values.AdminClientId} | ConvertTo-Json
[IO.File]::WriteAllText("$projectRoot\dist\config.js", "export default $config;",[Text.UTF8Encoding]::new($false))
Write-Host 'Frontend configured from deployed outputs.'
