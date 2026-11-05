param([string]$Region='us-east-1')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$account=aws sts get-caller-identity --query Account --output text
if ($LASTEXITCODE -ne 0 -or $account -ne '912010732788') { throw 'Sign in to AWS account 912010732788 first.' }
Write-Host 'Reusing KB 5KIGBYRICE, data source VPS3UHQOQC and thinkingai-datasourse-bucket.'
Write-Host 'The changeset should add ONLY Catalog, Grounding and GroundingVersion. No new KB, S3 source bucket, role or vector index.'
aws cloudformation deploy --template-file "$projectRoot\aws-backend\knowledge.yaml" --stack-name thinking-ai-knowledge --region $Region --no-execute-changeset
if ($LASTEXITCODE -ne 0) { throw 'Changeset creation failed.' }
Write-Host 'Review and execute ONLY this newly created changeset. Leave the previous changeset unexecuted. Wait for CREATE_COMPLETE, then run deploy-backend.ps1.'
