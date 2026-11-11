# Account settings API

`/api/v1/me/` reads and partially edits the current session account. Existing HTML
profile editing remains available and uses the same atomic edit service. This
JSON settings resource does not accept uploads, password changes or account deletion.
Image writes use the separate [multipart image resource](account-image-api.md).

## GET and response

GET/HEAD require a Django session. Anonymous requests return 403
`authentication_required`. Responses are private/no-store, vary on Cookie and
contain only the current account's explicitly allowed data:

```json
{
  "id": 123,
  "username": "example-user",
  "email": "user@example.invalid",
  "profile": {
    "measurements_format": "USA",
    "image_url": "/media/default.jpg"
  }
}
```

`image_url` is the configured storage URL, possibly relative. Reading it does not
open image bytes, check storage existence or upload files. An empty image field
returns null. Missing legacy profiles return `profile: null`; reads never create
or repair them. An unknown stored measurement value returns a null preference
without changing that stored value. The virtual account resource itself exists
for every authenticated account.

Password hashes, permissions, groups, staff/superuser flags, other accounts and
private player records are not included. Public statistics APIs remain independent
of account preferences and keep their canonical data units.

## PATCH

PATCH accepts a JSON object containing any subset of:

```json
{
  "username": "new-name",
  "email": "updated@example.invalid",
  "measurements_format": "Europe"
}
```

Omitted fields remain unchanged and are not revalidated. This allows a preference
change when an omitted legacy email is blank, and prevents model normalization
from silently saving omitted fields. An empty object is a no-op. Success returns
200 with the same current-account response shape.

- Username and email validation reuse `UserUpdateForm`. Username now uses Django's
  registration-compatible Unicode normalization and case-insensitive uniqueness,
  excluding the current account. HTML profile edits use the same policy. This
  intentionally closes the old profile editor's case-variant rename gap; existing
  case-variant accounts are not merged or renamed automatically.
- Email remains required/nonblank when supplied and **not unique**, matching the
  existing forms. Django's normal email-domain normalization applies. No new email
  verification or account-recovery policy is introduced.
- `measurements_format` is exactly `USA` or `Europe`, using the existing preference
  form. Other spellings/codes, blank and null are invalid. The saved preference
  continues to control existing HTML displays; public JSON statistics do not change.
- JSON username/email must be strings; numeric/boolean/null/collection values are
  rejected rather than coerced into text.

Session authentication and CSRF are required using the
[session bootstrap contract](session-auth-api.md). PATCH preserves the session,
CSRF token, password and last-login value. An email change naturally invalidates
older Django password-reset tokens because email participates in their hash.

Unknown fields, nested `profile` objects, account/profile selectors, `image`,
`image_url`, passwords and privilege fields return 400. Query parameters are
rejected on both GET and PATCH. Malformed JSON is 400; non-JSON update media types
are 415. PUT/POST/DELETE are not supported. Validation errors follow the standard
`invalid_parameters` envelope and leave all account/profile fields intact.

A missing profile returns 409 `account_profile_unavailable` on PATCH, even for an
empty update. It requires separate review; the API does not guess or backfill it.
A valid explicit preference replacement can correct an existing invalid preference.

## Transactions and concurrent edits

The service locks the normalized target username (when supplied), then the fresh
account row and profile row. Registration and both HTML/JSON profile writers use
the same PostgreSQL name-lock namespace. Competing case variants therefore cannot
be claimed by a rename and registration at the same time. Proven exact database
username collisions from noncooperating writers become username field errors;
unrelated database failures remain server errors.

User/profile changes and JSON response serialization are in one transaction.
Failed saves or serialization roll back account and preference changes. Only
submitted user fields are saved, and the signal handler sees the fresh profile;
stale snapshots cannot restore omitted password or preference fields through these
cooperating web flows. Reads take the account lock so their snapshot follows a
competing settings update. Different accounts do not share account/profile locks;
only competing normalized names can share a name lock.

The legacy HTML form remains a full form submission. Unlike PATCH, it can explicitly
replace all submitted settings, including values loaded before another request.
This lock is not a revision protocol; future clients must handle out-of-order
responses. Direct SQL/new writers must respect the shared lock rules. No new
case-insensitive database constraint or duplicate-account cleanup is introduced.

## Upload boundary and remaining work

The JSON settings endpoint exposes only a read-only image URL. The dedicated
[multipart avatar endpoint](account-image-api.md) now handles upload and default
reset. Multipart parsing is not enabled globally. Existing HTML uploads share the
new storage lifecycle and preserve their form policy. Compensating cleanup does
not provide a durable distributed database/storage transaction.

No migrations, dependency changes, loader calls or frontend implementation are
introduced here. Complete remaining search contracts before
Vue/Vite scaffolding. Legacy projection provenance remains a separate review.
