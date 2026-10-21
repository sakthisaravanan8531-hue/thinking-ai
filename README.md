# Thinking AI

Complete source for the live AWS-hosted general-purpose and document chatbot.

Live website: https://d3nv2zhw5ihk84.cloudfront.net/

## Project folders

| Folder | Purpose |
| --- | --- |
| `dist/` | Complete frontend: index.html, aws-client.js, markdown.js |
| `aws-backend/src/` | Python Lambda code and requirements |
| `aws-backend/template.yaml` | AWS SAM infrastructure |
| `aws-backend/tests/` | Mocked backend tests |
| `tests/` | Frontend client, UI and Markdown tests |
| `scripts/` | PowerShell deployment scripts |
| `.vscode/` | VS Code test tasks and optional extensions |
| `.github/workflows/` | GitHub Actions test workflow; no AWS auto-deployment |
| `docs/` | Editable draw.io architecture |

## Open in VS Code

Extract the ZIP. Select **File > Open Folder** and choose `thinking-ai-project`, the folder containing this README. The entire frontend and backend appear together in Explorer. Git is not needed to open and edit the project.

## Current behavior and architecture

CloudFront serves static files from a private S3 bucket using OAC. The browser sends questions to API Gateway, which invokes Lambda. Lambda reserves DynamoDB daily usage and invokes Google Gemini using a key from SSM Parameter Store. Cognito handles account registration, email verification and Pro sign-in. CloudWatch collects execution logs.

The active model is `gemini-3.5-flash-lite`. Bedrock is an optional inactive code path pending account access. The response includes the exact model ID. Both Free and Pro currently use the same model; Pro is account access, not a paid subscription.

Uploads wait for the user's instruction; no automatic AI summary. The browser extracts document text, holds it in tab memory and sends it with each explicit question. The document stays attached until Close Conversation, New Conversation, home, removal, refresh or sign-out. Projects/Recents navigation can restore a still-open document. Chats and projects are not persisted across refresh. Retrieval is bounded lexical passage matching, not a vector database. General chat does not send previous turns to the model.

### Current limits

- Free: 50 requests per network per UTC day, 100 shared Free requests.
- Pro: 40 requests per account per UTC day.
- Site: 100 requests per UTC day across both plans.
- Output: up to 1,024 tokens per answer.
- Document: up to 10 MB and 200,000 extracted characters; question: 2,000 characters.
- Selected document context: 12,000 characters maximum.

Uploading alone uses no AI quota. Submitted questions and explicitly requested summaries count; provider failures may also consume admission. Provider quotas and billing apply separately.

## Tests

Use Python 3.12 and Node.js 22+ (matching CI). From the project root:

```powershell
python -m unittest discover -s aws-backend/tests -v
node tests/live-client.mjs
node tests/live-ui.cjs
node tests/markdown.mjs
```

Tests mock AWS/provider requests and need no credentials or Gemini key. No npm dependencies or frontend build step are needed. VS Code **Terminal > Run Task** exposes the same test commands.

### Local layout preview

```powershell
python -m http.server 5500 --directory dist
```

Open http://localhost:5500. Live chat from this local origin is blocked by the current production CORS policy. Test interaction logic using the mocked tests, or explicitly add a localhost origin to the backend for live development. Do not disable browser security. Test the deployed app at the HTTPS website above.

## Reuse your existing AWS deployment

Do not create a second stack just to move this source to GitHub. AWS CLI and SAM CLI are required only for deployment. From this project root, copy your existing configuration:

```powershell
Copy-Item "$HOME\thinking-ai-setup\thinking-ai-backend\samconfig.toml" `
  ".\aws-backend\samconfig.toml"
```

The real config is ignored by Git. Alternatively review and copy `aws-backend/samconfig.example.toml` to `aws-backend/samconfig.toml`. This example targets your existing account resources and enables registration. Preserve deliberate changes from your current local config.

Deploy from the root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-backend.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-frontend.ps1
```

Backend deployment validates, builds and deploys the existing SAM stack; review its changeset. Frontend deployment uploads only `dist/`, then invalidates CloudFront. No backend source or docs are copied into the website bucket.

The CloudFront distribution, frontend S3 bucket, OAC/bucket policy and SSM key are external resources already configured separately. The SAM template manages the API, Lambda, Cognito, DynamoDB, IAM role and logs. SAM also uses a separate managed S3 bucket for code artifacts. New accounts must configure those external resources and update the frontend public API/client IDs, template origins, scripts and SAM config.

## GitHub without installing Git

1. Sign in to `sakthisaravanan8531-hue` and create a repository named `thinking-ai`. Choose Private initially unless you want the source public.
2. Choose **uploading an existing file**, or **Add file > Upload files** in an existing repo.
3. Open the extracted `thinking-ai-project` folder and upload its contents. This README and `dist/` must be at the repository root. Upload files, not the ZIP.
4. Include `.github/`, `.vscode/`, `.gitignore` and `.gitattributes` if Windows hides them.
5. Browser uploads do not honor `.gitignore`: use this clean export before adding local configuration. Never upload real credentials, `.aws/`, `.env`, keys, passwords, tokens, real samconfig.toml or build output.
6. Commit as `Add complete Thinking AI app`. GitHub Actions runs tests if enabled; it does not deploy AWS.

When Git becomes available, clone the repo and open it in VS Code for normal commit/push synchronization. VS Code alone does not automatically sync an extracted folder to GitHub.

## Optional Amplify later

The current hosting remains S3 + CloudFront. To deploy from GitHub with Amplify later, connect this repo, publish the `dist/` directory, then add the resulting Amplify HTTPS origin to API CORS. The existing backend can stay. No Amplify app is created by this package.

## Security

No API keys, AWS credentials or actual SAM config are included. Public API URLs, Cognito client IDs, bucket names and account/resource IDs are configuration identifiers, not credentials. Gemini keys stay in SSM, and Cognito tokens stay in tab memory. Documents are sent to AWS and the provider on explicit questions. Avoid confidential uploads; Gemini free-tier processing may be subject to product-improvement terms. No billing alarms or account-wide spending guarantees are implemented.

## Verification

The export passes 31 mocked Python backend tests and the three Node test suites. Actual PowerShell/SAM deployment and live browser behavior depend on your workstation and account. Exporting this folder does not change the existing live app.
