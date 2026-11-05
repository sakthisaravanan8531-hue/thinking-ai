# Original Knowledge Base migration guide

For the latest Bedrock-primary fallback deployment, follow **BEDROCK-FALLBACK.md** first. The steps below document the earlier base migration.

# Deployment with your EXISTING Knowledge Base

Confirmed resources:

| Resource | Existing value |
| --- | --- |
| Knowledge Base | `5KIGBYRICE` — data-source-rag |
| Data source | `VPS3UHQOQC` — data-source-ragchatboard |
| Source bucket | `thinkingai-datasourse-bucket` |
| S3 Vectors index | `bedrock-knowledge-base-m6ytf1/bedrock-knowledge-base-default-index` |
| Knowledge service role | `AmazonBedrockExecutionRoleForKnowledgeBase_po9bc` |

## 1. Replace the previous package

Extract this updated ZIP and use this folder in VS Code. Do NOT execute the previous knowledge-stack changeset: it creates duplicate infrastructure. The new template only adds `Catalog`, `Grounding`, and `GroundingVersion`. None of your existing Bedrock resources, objects, parsing or chunking settings are changed by CloudFormation.

Run tests from the project root:

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
node tests/markdown.mjs
node tests/workspace.mjs
```

## 2. Prepare the revised support-stack changeset

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-knowledge.ps1
```

This creates a NEW, unexecuted changeset for `thinking-ai-knowledge`. Review this NEW changeset in CloudFormation, us-east-1. It must add only the catalog table and grounding guardrail/version. Execute this new changeset, not the old one; wait for CREATE_COMPLETE. The existing Knowledge Base, source bucket, service role and vector index are referenced through stack outputs, not recreated or imported into CloudFormation ownership.

The catalog is retained on stack deletion. Your existing storage is outside this stack and remains under its existing ownership/lifecycle settings.

Your data source uses SEMANTIC chunking and BEDROCK_DATA_AUTOMATION with MULTIMODAL parsing. These settings are preserved. Parsing, semantic chunking/embedding, storage, retrieval and new grounding checks can consume credits; no exact free-tier assumption is made. If cost becomes an issue, review parser/chunking changes separately in Bedrock before reindexing. Do not silently change or re-create this source.

## 3. Update the backend and configure the existing source bucket

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-backend.ps1
```

This reads support-stack outputs and preserves your current provider, model, quota, output-token and pause settings. It configures CORS on the existing source bucket for POST uploads from your CloudFront origin, preserving its other CORS rules, and enables all four S3 Block Public Access settings. This assumes the bucket is dedicated to private application documents. Source objects and Bedrock ingestion configuration are not changed. Review your bucket policy separately if you previously granted other principals access.

The SAM changeset removes `/free`, adds authenticated staff/admin routes, creates a separate admin app client and four Cognito groups, disables self-registration and updates scoped Lambda permissions. Existing user pool/client/API/function logical IDs are preserved. Stop if user-pool replacement is proposed. The script ignores old Free/Pro/self-signup samconfig overrides.

After deployment, configure-site.ps1 fills in the public app-client IDs from outputs. Do not guess the admin client ID. The previous CI role may need a reviewed permission update for the one-time backend migration; use your current AWS CLI identity for these setup scripts.

### Existing documents must be assigned before staff can access them

Existing KB documents are deliberately hidden from staff unless they have both department/documentId metadata and an ACTIVE catalog record. They also do not appear in the admin list until registered. This prevents unclassified HR content from becoming visible to every department.

Either upload approved copies through the new admin portal, or register an existing object individually after the support stack has deployed:

```powershell
python .\scripts\register-existing-document.py --key "exact/path/policy.pdf" --department hr
```

Replace the key with its exact S3 object key and choose hr/cloud/genai yourself. The script preserves the source document, merges its metadata sidecar, writes its catalog record and starts sync. It refuses conflicting/deleted assignments. Wait for indexing before expecting answers. Re-run Sync after a running job completes if another job blocked the start. Never bulk-assign unknown documents to a department.

## 4. Assign users

Public signup is now disabled. Existing accounts receive no access until their groups are assigned.

In Cognito → user pool `us-east-1_VXXacSNo9` → Groups:

- Put each staff account in **exactly one** of `hr`, `cloud`, `genai`.
- Put administrator accounts in `admin` only. Use a separate staff account if the same person also needs department chat.
- Do not allow users to choose or edit their group.
- Keep app clients public with no client secret. API Gateway validates issuer/audience; Lambda checks token type, client and group.

For a new account (replace the sample values):

```powershell
.\scripts\invite-user.ps1 -Email "person@example.com" -Name "Team Member" -Department hr
.\scripts\invite-user.ps1 -Email "admin@example.com" -Name "Administrator" -Department admin
```

Cognito sends a temporary password invitation. The portal handles first-login password changes. Invitation delivery depends on Cognito email limits/verification settings. For existing accounts, assign groups through the console rather than attempting to create the account again.

The latest account-management update validates current account status/groups on every request and records security-change revocation timestamps. See ACCOUNT-MANAGEMENT.md for account creation, role changes and password recovery.

## 5. Publish frontend

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-frontend.ps1
```

This uploads only `dist/` to `thinking-ai-web-912010732788`, removes the obsolete `aws-client.js`, and invalidates distribution `E1Q60LVMJ9T8M9`. It leaves the bucket private and retains your OAC policy. Wait for the invalidation to complete.

Staff: https://d3nv2zhw5ihk84.cloudfront.net/

Admin: https://d3nv2zhw5ihk84.cloudfront.net/admin.html

## 6. Verify live behavior

1. Anonymous `/chat` and admin requests must return 401; `/free` must no longer invoke Lambda.
2. Sign in as an HR user. Upload/admin controls must be absent. General knowledge questions without document evidence must abstain.
3. Sign in through `/admin.html` using an admin account. Upload a short HR policy. Click **Check indexing** until COMPLETE; check failed-document counts. A running ingestion job can cause another upload to be queued: click **Sync knowledge base** once the current job completes.
4. Ask a question answered by the HR policy. Check its filename citations. Ask from a Cloud/GenAI account: it must not return HR content.
5. Delete the HR document. Answers from its old vector results must be blocked immediately, even before indexing finishes.
6. Refresh the tab: it must show login again. New Conversation clears current context and moves the prior chat to Recents; the live sidebar shows at most five messages.
7. Inspect CloudWatch for dependency failures without logging document content or secrets. Inspect DynamoDB usage counters and your billing console.

Your existing multimodal Bedrock Data Automation parser is preserved; parser/account access and ingestion success still need live verification. No autonomous retries, background sync queue, persistent conversation archive or account-management UI is included.

## Administration details

Staff cannot upload document bodies through `/chat`. Their department comes from the validated Cognito token, never a request parameter. Metadata sidecars are generated only by Lambda. The existing KB service role is preserved; review its existing S3/vector/model permissions. Staff receive no S3/IAM access from this application.

Uploads use five-minute S3 presigned forms restricted to the generated object key and declared file size, with a 50 MB application cap. Only admins can request them. The finalization endpoint checks the S3 object's size and writes department/document metadata. Admins are trusted document publishers; review files before uploading. A PENDING row from an interrupted upload is not searchable. Delete it through the admin list to clean up.

The app records deletion in the catalog before removing both source and metadata objects, then starts a KB sync. Stale KB passages fail the catalog check. S3/KB service failures can require another Sync; they never restore a deleted catalog record. Admin list shows ACTIVE for approved source records; actual searchability additionally requires completed KB ingestion. The indexing status is displayed separately.

IAM restricts the application Lambda to its document bucket, catalog table, usage table, KB, guardrail and configured secret/model. Never distribute Lambda execution credentials to staff. A person with direct AWS knowledge-base Retrieve permissions can bypass application-level department filtering; ordinary app users must have Cognito accounts only.

To roll back, use your previous source/CloudFormation templates deliberately. Restoring the previous backend also restores anonymous/general chat, so do not use that as a security-preserving rollback. To pause safely, set `AppEnabled=false` on the backend stack.
