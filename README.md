# Thinking AI — department document workspace

The department workspace uses **Bedrock primary with text search and Gemini fallback**. See the [editable architecture diagram](docs/Thinking-AI-Architecture.drawio) and the [fallback deployment guide](docs/BEDROCK-FALLBACK.md).

## Current behavior

- Cognito sign-in required. Staff have exactly one active department; admins have a separate login/app client.
- Admins manage documents, accounts and departments. Staff cannot upload/delete or manage accounts.
- One Recents list holds current and ended conversations in tab memory. Enter sends; Shift+Enter adds a line. Refresh/sign-out clears the session and requires sign-in.
- Up to 50 MiB per upload, with one or more selected departments. Each selected department has its own approved source/catalog record.
- Bedrock Knowledge Bases + configured Bedrock model + grounding check are primary when fallback is enabled.
- On availability failures, keyword search over a private text index supplies authorized evidence to the existing Gemini model. Search tolerates common typos. Gemini can explain topics found in approved documents; the server verifies exact source excerpts and checks citations before returning the answer.
- Current Cognito status/group checks, department availability, revocation timestamps and daily quotas apply to both paths. Deleted sources are denied before any stale index can be used.
- Explicit model safety refusals and grounding interventions never trigger another provider afterward.

## Open in VS Code

Open this entire folder, not only dist/. Read the relevant deployment guide before uploading files.

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
node tests/workspace.mjs
node tests/markdown.mjs
```

## Enable the fallback update on the existing AWS project

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-backend.ps1 -EnableFallback
```

Review its changeset: a private cache bucket/policy, background indexing worker/role/logs/async configuration, and scoped updates to the existing API/Lambda. No source bucket, Knowledge Base, vector index or Cognito user pool should be replaced. Then deploy the frontend:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-frontend.ps1
```

After invalidation, sign in as admin and select **Build fallback index**. Wait for READY/PARTIAL status using Refresh documents. Existing approved documents do not need re-uploading. New approved uploads queue indexing automatically.

## Limits and costs

The app preserves your current model identifiers, output-token budget, global/user request allowances and pause setting. EnableFallback explicitly chooses Bedrock primary and allows the existing configured Gemini fallback; no new provider key or paid model tier is created.

Fallback extraction is limited to 250 PDF pages and 250,000 text characters per source; a partial index is labeled. Scanned PDFs require OCR, which is not added. Keyword search is less flexible than semantic retrieval. Up to 50 active records can be searched in a department or indexed in one admin operation.

IndexDailyLimit defaults to 20 worker batches per UTC day (up to 10 records per batch). These are cost controls, not a guarantee of free operation. Lambda, S3, DynamoDB, logs and your configured external model can consume credits/allowances. No NAT, OpenSearch cluster or provisioned model capacity is added. The cache is private/encrypted and retained on stack deletion; remove retained storage deliberately when no longer needed.

Only authorized excerpts and bounded conversation context are sent to Gemini. Confirm your organization's policy permits the configured Google service/tier for the document data you upload.

## Guides

- BEDROCK-FALLBACK.md: activate the fallback, extraction/search limits, retry/cost behavior and live checks.
- DEPLOYMENT.md: original migration using your existing KB/source.
- ACCOUNT-MANAGEMENT.md: admin user controls and password recovery.
- RECENTS-DEPARTMENTS.md: conversation sidebar and dynamic departments.
- MULTI-TEAM-UPLOADS.md: 50 MB uploads and independent team copies.
- VALIDATION.md: checks performed and live verification limits.

Your private Sites UI-review mock is separate and is not connected to this backend.
