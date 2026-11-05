# Verification

Passed locally on 29 October 2026:

- 100 Python security and infrastructure tests: login/client/group checks, removed anonymous route, upload rejection, department filtering, catalog and source location checks, missing evidence, grounding rejection, invalid citations and deletion during generation.
- Node frontend interaction checks: login gate, separate admin client, question-only payload, five-message context and sidebar, Recents and logout.
- Safe Markdown rendering checks, including HTML/script/URL injection handling.
- JavaScript syntax and Python compilation.
- cfn-lint validation of both AWS templates, including the SAM transform.

Not executed here: Windows PowerShell scripts, AWS SAM build/deploy, live Cognito login, S3 upload, Bedrock ingestion/retrieval/grounding, Gemini generation, browser visual rendering or the GitHub workflow. These require your environment or credentials. Follow DEPLOYMENT.md acceptance steps before production use.

The reuse update also checks that only the catalog and grounding resources are created; the confirmed existing KB, source and bucket are passed through outputs. The bucket configuration and document-registration scripts still require live verification.

The account update adds mocked Cognito invitation/role/self-protection/revocation/reset/delete tests and UI account/password-recovery interaction checks. Real email delivery and Cognito account mutations remain untested here.

Multi-team upload tests cover the exact 50 MiB boundary, oversized rejection, required/valid team selections, per-team metadata and server copies, idempotent publishing, and deleted-copy protection. Browser-module tests cover team selection and one browser upload. Real 50 MB transfer and S3 server-copy timing require live testing.

Department tests cover custom group creation, reserved/duplicate IDs, dynamic uploads/account roles/staff access, disable/enable, renaming, built-in group protection, populated-department deletion refusal and member pagination. UI tests cover unified current/saved Recents, Enter/Shift+Enter/IME, department creation and dynamic selectors. Actual browser rendering and live AWS operations require deployment verification.

The fallback update verifies Bedrock primary selection, shared cooldown, no provider switch after safety refusals, no model call without evidence, exact-quote/citation checks, active/deleted document checks, text/DOCX/PDF extraction, source ETag validation, OCR failure, bounded indexing admission, duplicate worker claims and deleted-cache cleanup. Cloud services/model calls are mocked. Native CloudFormation/SAM template linting passed; Windows SAM deployment and live model/IAM behavior are not yet verified.
