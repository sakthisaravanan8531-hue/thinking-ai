param([Parameter(Mandatory=$true)][string]$Email,[Parameter(Mandatory=$true)][string]$Name,[Parameter(Mandatory=$true)][ValidateSet('hr','cloud','genai','admin')][string]$Department,[string]$Region='us-east-1')
$ErrorActionPreference='Stop'
$attributes=@(@{Name='email';Value=$Email},@{Name='email_verified';Value='true'},@{Name='name';Value=$Name})
$file=Join-Path $env:TEMP ('thinking-ai-user-'+[guid]::NewGuid().ToString()+'.json')
try {
 [IO.File]::WriteAllText($file,(ConvertTo-Json -InputObject $attributes -Compress),[Text.UTF8Encoding]::new($false))
 aws cognito-idp admin-create-user --user-pool-id us-east-1_VXXacSNo9 --username $Email --user-attributes "file://$file" --desired-delivery-mediums EMAIL --region $Region --query 'User.Username' --output text
 if ($LASTEXITCODE -ne 0) { throw 'User creation failed. For an existing user, assign exactly one group through the Cognito console.' }
 aws cognito-idp admin-add-user-to-group --user-pool-id us-east-1_VXXacSNo9 --username $Email --group-name $Department --region $Region
 if ($LASTEXITCODE -ne 0) { throw 'Group assignment failed. Account has no workspace access until assigned.' }
 Write-Host "Invitation sent. $Department portal access assigned."
} finally { Remove-Item $file -ErrorAction SilentlyContinue }
