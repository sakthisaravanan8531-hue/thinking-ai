# 50 MB uploads for one or more teams

Apply the update ZIP at the project root, then deploy backend first and frontend second using the existing scripts. No new AWS resources or IAM actions are required; existing GetObject/PutObject permissions cover server-side S3 copies.

- Admins must select at least one of HR, Cloud and GenAI. They can select two or all three.
- Both frontend and backend accept documents up to 50 MiB (52,428,800 bytes). The presigned S3 form also enforces the declared size. Finalization checks the actual source size.
- The browser transfers the file once, directly to S3. Lambda makes a separate S3 copy for each additional selected team, without downloading the document into Lambda memory.
- Each copy has its own catalog ID and scalar department metadata. Existing retrieval filters and catalog checks are unchanged. Unselected teams cannot retrieve the document through the application.
- The admin list displays a separate row for each selected team. Deleting a team row removes only that team's copy. To remove all copies, delete each listed team row.
- Copies are immutable after publication. Retrying publication uses deterministic IDs, skips already active copies and never recreates copies marked DELETED. Conditional catalog writes protect tombstones during publication races.
- If a publishing request fails after the file has uploaded, the current tab offers Retry publishing and locks the file/team selection. It reuses that file instead of uploading another copy. This pending-upload state is held in memory only; a refresh/sign-out clears it. An interrupted source may remain PENDING and can be removed from the admin document list.
- Shared documents use more S3 storage and separate ingestion per team. Once Bedrock is enabled, parsing/embedding costs can increase with each selected team. No automatic sync retry queue is added.
- Bedrock quotas remain blocked. Upload/catalog publication can complete, but indexing remains PENDING and staff document answers remain unavailable until retrieval works.

Deployment:

```powershell
Expand-Archive "$HOME\Downloads\thinking-ai-50mb-team-upload-update.zip" -DestinationPath . -Force
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-backend.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-frontend.ps1
```

After invalidation, Ctrl+F5 the admin portal. Verify one small file shared with two teams, then a larger file under 50 MB. Use existing unwanted duplicates to verify independent deletion; do not remove real approved documents merely to test. Actual large-file S3 copy latency and AWS quota behavior have not been tested in this workspace.
