# Profile image API

The current account's avatar has a dedicated multipart resource:

| Method and route | Result |
| --- | --- |
| `PUT /api/v1/me/image/` | Replace the image and return the current account snapshot, 200 |
| `DELETE /api/v1/me/image/` | Restore the configured default, 204 including already default |

Read the current image URL through [GET `/api/v1/me/`](account-api.md). GET/POST/PATCH
on the image resource return 405. No account selector or query parameters are
accepted. A Django session, CSRF and an existing profile are required. Anonymous
requests return 403 `authentication_required`; a missing profile returns 409
`account_profile_unavailable` without creating records or publishing files.
Responses are private/no-store and vary on Cookie. File serving itself continues
to use the existing media/storage configuration.

## Upload contract

PUT must use `multipart/form-data` with **exactly one `image` file**. Text values,
duplicate files and all additional fields are rejected. JSON or raw image-body
uploads are 415. Use FormData in the future frontend and let the browser generate
the multipart Content-Type/boundary. Send the session cookies and the token from
the [CSRF bootstrap](session-auth-api.md).

The API accepts complete still **PNG, JPEG or WebP** images with these bounds:

- At most **5 MiB** of file content.
- At most **20 million pixels**.
- At most **8192 pixels** in either dimension.
- One frame; animated files are rejected.

Pillow verifies the file and fully decodes it within these bounds; the existing
profile image field validation also applies. Empty, malformed, truncated, unsafe
pixel-size and unsupported image inputs return 400 with `image` field errors.
The declared MIME type and client filename do not determine the stored format.
Names such as `photo.html` cannot choose a storage path: the service generates a
unique UUID filename with an extension matching the detected image format.

Original bytes are retained. There is no resizing, cropping, recompression or
metadata removal. Validation bounds apply to the parsed file; deployment request
body limits remain the web server/proxy's separate responsibility.

Success returns the [account snapshot](account-api.md), including the new
`profile.image_url`. Username, email, measurement preferences, password, last-login
and sessions are unchanged by the image update. Repeating an upload may generate
a new URL, while retaining one active image and cleaning the replaced managed file.
No automatic mutation retry policy is introduced.

DELETE accepts an empty body or empty JSON object and has no response body. It
restores the Profile field's configured default (`default.jpg` in the current
model), preserves all other settings, and never deletes the shared default file.
Account PATCH remains JSON-only and continues to reject image fields/files; the
multipart parser is enabled only on this resource.

## Storage lifecycle and concurrent edits

API uploads/reset and HTML profile uploads share file lifecycle handling. Account
and profile locks cover staging/publication, database writes and API response
serialization; the existing account editor uses the same lock order. Competing
uploads, reset and preference changes serialize per account. Different accounts
do not share account locks.

A file is saved under a fresh managed name before its reference is published.
Failed saves, response serialization or handled savepoint failures remove new
files that are no longer referenced. Old image files are scheduled for cleanup
**only after the database commits**, and deletion checks all Profile references.
Another profile's shared reference protects a file until the last reference is
removed. Default files and names outside the managed `profile_pics/` namespace
are preserved. No storage `.path` access is required; storage-returned filenames
are honored.

Deletion failures are logged as `Profile image cleanup failed` and do not turn a
committed successful update into a false HTTP failure. Cleanup is compensating,
not a durable database/storage transaction: process crashes, unavailable storage,
unknown names created by a failing backend, or an independently managed outer
transaction can leave residual files. No automatic orphan sweep is implemented.
Future writers must use the same owner lock and image lifecycle rather than saving
image names or bytes directly.

A legacy User post-save signal also needed narrowing: field-limited User updates
(such as `last_login`) no longer save a cached Profile implicitly. This prevents
login or stale field-limited account saves from restoring an old avatar. Explicit
profile editors save their freshly locked Profile themselves.

## HTML compatibility and remaining work

Existing HTML forms retain their image validation/format policy and original-byte
storage. The API's tighter still-image/size limits apply to this new endpoint,
not retroactively to legacy form choices. HTML uploads now receive the same staged
file cleanup, post-commit old-file deletion and generated storage names. An invalid
combined form leaves the account and stored avatar intact.

No migrations, dependency changes, new storage backend or frontend implementation
are introduced. Remaining search contracts precede Vue/Vite scaffolding; legacy
projection provenance remains a separate review.
