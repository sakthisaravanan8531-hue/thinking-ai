# Bedrock primary with a document fallback

This update is source code and deployment tooling, not an already activated AWS change. It preserves your existing Cognito accounts/groups, department registry, document catalog, source bucket, Knowledge Base and vector index.

## Activate

From the project root:

```powershell
Expand-Archive "$HOME\Downloads\thinking-ai-bedrock-fallback-update.zip" -DestinationPath . -Force
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-backend.ps1 -EnableFallback
```

Review the changeset before approving. It adds a **private fallback index bucket**, its TLS policy, **IndexWorker** with its scoped role, a three-day worker log group, async invocation configuration, and an authenticated admin indexing route. It updates the existing API/Lambda/role. No user pool, source bucket, Knowledge Base or vector store should be replaced.

`-EnableFallback` explicitly sets `PrimaryProvider=bedrock` and `DocumentFallbackEnabled=true`. It preserves your existing Gemini model/key parameter, question/token quotas, pause state, source/KB IDs and department settings. Later ordinary deployments preserve these two new fallback parameters and the daily indexing limit. It does not enable billing or change the Google model/tier.

After backend deployment succeeds:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-frontend.ps1
```

Wait for invalidation and refresh with Ctrl+F5. Sign in as admin, open Documents, and click **Build fallback index**. This queues existing ACTIVE approved document records. They do not need to be uploaded again. Unregistered legacy S3/KB objects remain inaccessible: register or re-upload them only after assigning their department.

Click **Refresh documents** to check the text-search state. READY is complete; PARTIAL means the configured extraction ceiling was reached. FAILED shows a non-content error code. New uploads automatically queue indexing after their approved department copies are published. A **Rebuild text index** button retries an individual document, including a changed source or missing cache.

## Request behavior

1. Every request still validates Cognito client/group, current account status, department availability, revocation timestamp and daily user/site allowance.
2. If the shared cooldown permits, retrieve authorized passages from Bedrock Knowledge Bases, generate using the configured Bedrock model, then run the existing Bedrock grounding check.
3. A known availability failure (including quota throttling, unavailable model or inaccessible KB) starts a five-minute cooldown in the existing usage table. Later requests use fallback during that period; the next request after expiry probes Bedrock again. Multiple simultaneous first failures are still possible before the cooldown is saved.
4. When KB retrieval fails or returns no authorized passages, search the private extracted-text indexes for ACTIVE documents in the user's department. Validate the cached department, document ID, source key and current S3 ETag. No user-supplied department or source text is accepted.
5. If Bedrock generation/grounding is unavailable after retrieval succeeds, reuse those authorized passages rather than searching again.
6. Gemini explains topics found in the authorized passages, labels background information, and provides exact source excerpts as JSON. The server normalizes PDF whitespace, verifies excerpts and checks citations before returning the explanation. Search supports common typos when the approved text provides a clear match.
7. Recheck the catalog before returning citations. Deleted or reassigned documents fail closed. A current safety refusal or explicit guardrail intervention stops the request; it never triggers another model afterward. A malformed/unsupported primary answer also abstains rather than trying another model.

The fallback is **keyword search plus verified excerpts**, not semantic/vector search. General-purpose answers remain disabled. Empty search results do not call Gemini. If indexes are missing/pending, users get an indexing message rather than fabricated answers. The UI identifies the actual model and fallback text-search mode. Partial search coverage is indicated under the composer.

## Extraction limits

- Source formats: PDF, DOCX, UTF-8 TXT/Markdown; maximum source size 50 MiB as before.
- Background worker: 1,024 MB memory, 120-second timeout. Browser uploads remain direct to S3; PDF parsing does not happen in the 28-second chat Lambda.
- At most 250 PDF pages and 250,000 extracted characters per document. Limits produce PARTIAL state. DOCX main document XML is limited to 20 MiB and parsed with entity expansion disabled.
- Scanned/image-only PDFs need external OCR; this implementation does not charge for or invoke an OCR service. Encrypted PDFs, malformed files and excessively complex pages fail indexing.
- Search supports at most 50 ACTIVE documents per department. A bulk admin indexing operation supports up to 50 ACTIVE records across its scope; archive unwanted records first if that limit is exceeded.
- Jobs contain at most ten document IDs. Per-batch extraction reuses identical ETag/format content where possible. One worker keeps only one extracted file cached at a time.
- Duplicate worker deliveries claim a QUEUED document conditionally. They cannot reactivate DELETED records. A source changed during extraction is not activated. Deleted-document index cleanup is retried from the admin list if it fails.
- Function-error retry count is zero and async queue age is one hour. AWS can still redeliver asynchronous events or delay throttled/system-error events within that age; worker claims are idempotent. If a timeout/OOM leaves INDEXING, manually rebuild after five minutes. Jobs are not automatically retried by the application.

## Cost controls

Existing global/user daily request limits and output-token cap remain unchanged. Gemini is attempted once per fallback answer, with the same SSM key/model; there is no paid-model escalation. Confirm your Google project/tier has the allowance you intend: the app cannot guarantee a free external API tier.

`IndexDailyLimit` defaults to **20 batches per UTC day**, with up to ten source records per batch. Failed/partial indexing jobs can still count toward it. This bounds admitted indexing work, not the total AWS bill. The new worker, S3 cache, DynamoDB operations and logs are usage-based and can consume credits. No NAT gateway, OpenSearch cluster, provisioned model capacity or embedding model is added for fallback.

The cache bucket is private, encrypted with SSE-S3, and retained on stack deletion/replacement. Retention protects document-derived data but retained storage continues until you deliberately remove it. The worker can read source documents and update only DOC# catalog records; it cannot call models, read the Gemini key, manage users, or edit department/account-security records. The chat Lambda can read/delete cache objects and invoke only the designated worker.

Only approved excerpts, the question and bounded chat context go to Gemini. Verify your organization's policy permits the configured Gemini service/tier, especially for confidential HR data. This is the same external provider you previously configured; no new provider account or secret is created.

## Verify in AWS

1. Build a small TXT or readable PDF index; confirm READY. Ask a question whose answer appears in it and verify the exact excerpt/filename.
2. With Bedrock quotas at zero, confirm text-search mode works and a cooldown entry appears at `CIRCUIT#bedrock` in the usage table.
3. Ask from a different department; that source must not appear. General knowledge questions must abstain when no relevant evidence exists.
4. Delete a source and repeat the question; cached answers from that source must stop. Check both source and derived index cleanup.
5. Test a scanned PDF and a larger text PDF; verify FAILED or PARTIAL is honest, without fabricated OCR or complete-coverage claims.
6. When Bedrock access returns, wait for cooldown expiry and verify the primary path. Keep fallback enabled for future availability failures.

No real AWS deployment, email/account mutation, document transfer or model invocation was performed while preparing this package. Local tests use mocked cloud services and small parser fixtures. Live IAM, Lambda packaging, PDF memory/latency, external model quotas and answer quality still require your deployment tests.
