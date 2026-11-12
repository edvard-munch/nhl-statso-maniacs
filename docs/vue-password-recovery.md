# Vue password recovery

The sign-in page links to `/password-reset` for requesting instructions. Trusted
email links can target `/recover-password/#uidb64=...&token=...` for confirmation.
Both views use the existing generated recovery API and shared session/CSRF/action
lock. No backend schema, email delivery service or password policy changes here.

## Enable the correct email destination

Until the frontend is actually served at the trusted public origin, keep the
backend's `PASSWORD_RESET_FRONTEND_PATH` empty so email continues using the
existing Django HTML confirmation. The Vue route existing in source alone does
not activate deployment routing.

When the frontend route is served there, configure:

```dotenv
PASSWORD_RESET_PUBLIC_ORIGIN=https://stats.example.com
PASSWORD_RESET_FRONTEND_PATH=/recover-password/
DEFAULT_FROM_EMAIL=accounts@example.com
```

Use the real served origin/authorized sender and existing mail-backend settings.
For DEBUG loopback development, the public origin can be the Vite origin
`http://127.0.0.1:5173`, with Django behind its existing same-origin proxy.
Missing/unsafe configuration yields uniform `password_reset_unavailable`; the UI
shows an unavailable state. This commit changes no local `.env` or server settings
and sends no real email during tests. See the [API contract](password-recovery-api.md).

## Request and acknowledgement

The email form uses required/email input affordances and server field errors.
Accepted requests show the same conditional acknowledgement for eligible and
unknown/inactive/unusable-password addresses. It does not confirm account existence,
matching-account count or delivery, and does not display the submitted email after
acceptance. Choosing another request is explicit. The backend's synchronous
matching/delivery behavior is unchanged; no constant-time guarantee is added.

A CSRF failure refreshes only the caller's token/session, requiring an explicit
new action. Lost/timed-out requests may already have caused email delivery; the UI
asks the user to check email before choosing another request. It never automatically
resends mail. Auth serialization and ten-second deadlines prevent duplicate actions
and indefinite waiting. The form email clears on success/unmount.

## Transient reset link and navigation

Before creating the router, the app captures an exact UID/token fragment and
replaces the current URL/history state with the clean path. Only nonempty, bounded,
unique `uidb64` and `token` fields are accepted. Duplicate, missing, oversized or
unexpected fields and query-based tokens are rejected. Misplaced UID/token query/
fragment values are scrubbed, not forwarded in auth return links. A wrong query-based
URL may already have reached the web server; always use the configured fragment
format rather than putting credentials in paths/queries.

A single-use in-memory handoff supplies the confirmation view. Raw credentials are
not hidden form fields, router context, browser storage or request URLs. A router
guard also captures/scrubs a new reset fragment opened in the same document,
replacing the view context before validating that new link. Clean router history
bookkeeping contains no reset credentials. Header/auth links remain clean.

The active view retains credentials only for link checking and explicit confirmation.
Success, invalid-link results and unmount clear them. Reloading the clean URL or
leaving and returning to the view requires reopening the original email link; no
secret is restored from history/storage. Server expiry/consumption remains
independently authoritative. No target identity is guessed from the UID.

## Validation and password change

After session/CSRF readiness, the view checks the link once with the non-consuming
validation POST. Invalid/expired/used/wrong-account links share one generic result.
Recoverable check failures have an explicit **Check link again** action. Neither
validation nor a later invalid link proves that a previous password change succeeded.

The form submits both exact new-password strings and UID/token in JSON to the
query-free confirm endpoint. Password/confirmation/strength errors retain their
server placement and do not consume the link. Both password fields clear after an
attempt. A CSRF rejection can be corrected only with another explicit submit.

Known successful confirmation shows **Password changed** and an explicit sign-in
link, with no automatic login. Session/CSRF rediscovery follows because the caller
may be the target whose old session is now invalid, or another still-authenticated
account. Failed rediscovery does not erase known password-change success; the
header instead remains unavailable until rechecked.

Uncertain confirmation clears entered passwords and does not replay the write.
The user can try signing in, request new instructions or explicitly revalidate the
link before choosing another submission. A failed revalidation does not manufacture
a success message. Late callbacks cannot update an unmounted view or disposed app.

## Checks and next phase

`make frontend-test` covers token parsing/handoff, request privacy, generic responses,
field filtering, successful/uncertain confirmation, caller-session reconciliation,
serialization and deadlines. `make frontend-test-browser` uses synthetic links and
intercepted APIs at desktop/mobile sizes for complete flows, no secret URLs/history/
storage, exact passwords, invalid/reused links, reload behavior and in-place links.
No application database, real account/email or NHL service is used. Existing isolated
backend tests remain the evidence for actual token expiry, atomic password changes,
session invalidation and concurrent consumption.

The session/login/registration/recovery UI phase is complete. Next implement the
season-scoped Players catalogue, filtering/sorting/pagination and URL state through
the existing APIs. Private-resource guards/caches, production recovery rate limits,
email activation and route cutover remain separate work.
