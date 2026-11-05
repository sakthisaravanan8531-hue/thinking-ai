# Unified Recents, Enter to send and department management

## Deploy

From your existing project root, extract this update ZIP and deploy backend first, then frontend:

```powershell
Expand-Archive "$HOME\Downloads\thinking-ai-recents-departments-update.zip" -DestinationPath . -Force
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-backend.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-frontend.ps1
```

Backend changes: add `ChatFunctionAdminDepartmentsPermission`, update API, Lambda code/environment and scoped role permissions for Cognito CreateGroup/GetGroup/DeleteGroup/ListUsersInGroup on your existing user pool. No new buckets, Knowledge Bases, vector indexes, user pools or tables are created. No existing users are reassigned. Review the changeset and stop if existing storage or user-pool replacement is proposed.

Wait for CloudFront invalidation, refresh with Ctrl+F5 and sign in again.

## Staff workspace

- The sidebar has one **Recents** list. A current chat appears there as soon as its first message is sent, with its first question as the title.
- The current conversation is highlighted. Further messages update the same entry; duplicate chat entries are not created.
- New Conversation saves the old conversation in Recents and starts an empty one. Clicking a recent chat restores its messages and moves it to the top.
- The separate Live conversation section is removed. The request still includes at most five previous messages as untrusted context.
- Enter sends a nonempty message. Shift+Enter adds a line. IME composition does not trigger sending. Sending is blocked while a request is already running.
- Conversations remain in the current tab's memory, as before. They survive ending a conversation within this session, but not a refresh/sign-out. No durable conversation database was added.

## Admin workspace → Departments

Create a department with a display name (e.g. Finance) and a permanent ID (e.g. finance). IDs must be 2–32 lowercase letters/digits/hyphens, beginning with a letter. Reserved admin/system IDs and reused/retired IDs are rejected. Up to 50 departments are supported.

A new custom department gets a Cognito group and an entry in the existing catalog's `CONFIG#DEPARTMENTS` record. The app uses conditional revision checks to avoid overwriting concurrent department changes. If creation succeeds in Cognito but a later registry write fails, repeat the same create request: only a group with this application's exact management marker can be recovered. Other pre-existing Cognito groups are never adopted automatically.

Active departments populate both upload-team checkboxes and account-role options. Uploads can target up to ten active teams at once; staff can only use their assigned department. The 50 MB limit and separate per-team source copies remain in place.

Controls:

- **Save name** changes the display name without changing the permanent ID, Cognito membership, document keys or evidence metadata.
- **Disable** prevents staff access, new role assignments and new upload preparations for that department. Existing accounts/documents are retained.
- **Enable** restores department availability.
- **Delete empty department** is available for custom departments. All accounts (including disabled ones) must first be reassigned/removed, and approved/pending document copies must be deleted. The app checks member and document pagination. Delete retires the ID permanently. A failed Cognito deletion leaves the department in DELETING, with a retry control; staff access stays blocked.
- Built-in HR/Cloud/GenAI groups remain managed by the existing CloudFormation template. They can be renamed or disabled, but the portal does not delete them and introduce CloudFormation drift.

Department status is checked on the backend, including current staff requests. Existing live Cognito role checks and account-revocation timestamps remain enabled. Ordinary users cannot access `/admin/departments`.

The older PowerShell invitation helper and existing-document registration helper still target the original built-in departments. Use the admin portal for custom department accounts and uploads.

## Test after deployment

1. Send a question (Bedrock may still return unavailable), confirm it immediately appears in Recents, then create a new conversation and reopen the old one.
2. Check Enter sends; Shift+Enter adds a line.
3. Create a test department. Confirm it appears in uploads and account roles; invite a test user into it.
4. Disable the test department and confirm its staff account cannot access the workspace. Re-enable to restore availability.
5. Reassign/remove test users and delete its unwanted document copies; delete the empty custom department.

Local security, routing, UI interaction and HTML checks passed. Live Cognito group operations and Windows deployments still require your environment. No AWS resources, groups or users were changed while preparing the package. Bedrock embedding quotas remain zero; document answers stay pending.
