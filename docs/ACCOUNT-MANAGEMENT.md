# Admin accounts and roles update

## Deployment

Extract the update ZIP into the existing `thinking-ai-professional` project folder. The paths inside the ZIP are relative to that folder.

Run backend first, then frontend:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-backend.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-frontend.ps1
```

Expected backend changes: add `ChatFunctionAdminUsersPermission`, update API, Lambda environment/code, and its scoped Cognito permissions. Existing users, app clients, KB, buckets and groups are preserved. Stop if an existing user pool or storage resource would be replaced. No change to the knowledge/support stack is needed.

After CloudFront invalidation, refresh with Ctrl+F5 and sign in to `/admin.html`. Select **Accounts & roles**.

## Included controls

- Create an account with name, work email and exactly one role: HR, Cloud, GenAI or Administrator. Cognito generates the temporary password and sends an email invitation. The application never returns that password.
- View accounts, including disabled and unassigned users; load more in pages of 20.
- Update display names or replace the managed department/admin role.
- Enable/disable accounts.
- Send a password reset code; users complete it through **Reset password** on either login page. Passwords and codes go directly from the browser to Cognito, never the app Lambda.
- Resend invitations for accounts still in FORCE_CHANGE_PASSWORD.
- Permanently delete another account after confirmation. This does not delete documents.
- The current administrator cannot edit, disable, reset, reassign or delete their own account through these controls. Use a separate authorized administrator or Cognito console for self-maintenance. This is self-protection, not a transactional guarantee that concurrent administrators cannot remove each other.

No new departments/groups or arbitrary AWS/IAM roles can be created. The app manages only hr/cloud/genai/admin membership in your existing user pool. Names appear after a fresh sign-in. Email addresses are not editable in this version.

## Enforcement

The new `/admin/users` endpoint requires the admin app-client ID and administrator group. Lambda permissions are restricted to the existing user-pool ARN.

Every staff/admin API request now reads the current Cognito account enabled/status and group membership. It checks the current role against the token's role. Role changes therefore require fresh authentication, and deleted/disabled accounts are denied further requests. If the identity service or catalog is unavailable, access fails closed.

Role changes, disable, reset and delete also save a revocation timestamp in the existing catalog under an ACCESS# key. A token authenticated at or before that timestamp is rejected even if the account is later re-enabled or completes recovery. Users may need to wait one second before signing in again because Cognito auth_time is expressed in seconds. Existing in-flight requests are not canceled.

No passwords, reset codes or tokens are logged. Account-operation audit events record action, administrator subject and target subject, with the existing three-day log retention. This is an application audit trail, not an immutable compliance audit system.

Email delivery depends on your current Cognito/SES settings and daily sending limits. Invitation delivery failures can leave a newly created but unassigned account; refresh Accounts, assign the correct role and resend its invitation. Never assign an unknown account a role automatically.

## Document status while Bedrock is blocked

Uploads still register approved sources, but they are not searchable until ingestion completes. Bedrock quota failures now return **Indexing: PENDING** instead of replacing successful upload/deletion with an unrelated generic failure.

Delete writes a DELETED catalog record before touching S3. Retrieval continues rejecting that record immediately. Successful S3 cleanup hides the record; vector cleanup remains pending until a later sync. If S3 cleanup fails, the DELETED record remains visible with **Cleanup pending**, so an admin can retry Delete. S3 multi-delete partial errors are treated as failures too.

No automatic background retry queue is created. Retry manually when the relevant service becomes available. Keep Bedrock embedding requests paused while your quotas remain zero.

## Verification

1. Log in as admin. Create a test account, then verify the emailed invitation and first password-change flow.
2. Log in as that staff user. Confirm the chosen department. Staff cannot use `/admin/users` or the admin portal.
3. Change its role while its staff tab is open. Its next API request must require fresh login; the new department appears after login.
4. Disable it. Sign-in/API access must fail. Enable it again and authenticate afresh.
5. Send a reset code and complete Reset password on the login page; authenticate with the new password.
6. Self-modification controls are disabled, and backend self-modification requests return 409.
7. Delete the test account; it must no longer authenticate. Do not delete real accounts merely to test this.
8. Delete an unwanted duplicate document. With Bedrock blocked, source removal should succeed and index sync should be PENDING.

Local tests mock Cognito, S3 and Bedrock. Live account changes, email delivery and Windows deployment scripts require verification in your environment. No accounts were created or deleted while preparing this update.
