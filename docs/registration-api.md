# Registration JSON API

`POST /api/v1/auth/register/` creates an account and its default profile using the
same `UserRegisterForm` as HTML registration. It shares the
[session/CSRF foundation](session-auth-api.md): anonymous and signed-in callers
must supply a valid CSRF token and corresponding cookies. No NHL requests occur.
Existing HTML registration keeps its form, messages and login redirect, and now
uses the same atomic persistence service.

## Request and result

Obtain a token from `/api/v1/auth/csrf/`, then submit JSON with `X-CSRFToken`:

```json
{
  "username": "example-user",
  "email": "example@example.invalid",
  "password1": "<chosen password>",
  "password2": "<chosen password>"
}
```

All four fields are required strings. Replace the password placeholders with the
same chosen value. `application/json; charset=utf-8` is supported. Form/multipart
submissions return 415 even if CSRF middleware has already consumed their stream.
No query parameters or additional body fields are accepted, including privilege,
profile/image, redirect or account-state fields.

Success is JSON 201:

```json
{
  "user": {"id": 123, "username": "example-user"},
  "login_required": true
}
```

The returned identity belongs to the **new account**, not necessarily the caller's
current session. Registration never automatically signs in or switches accounts.
An anonymous caller remains anonymous; a signed-in caller keeps their original
session, private session data and owned memberships. Use session discovery when
needed, then explicitly log in with the new credentials. Registration does not
rotate CSRF, so the bootstrap token remains usable for that login; successful login
returns a fresh token as documented in the session contract.

No password/hash, email, staff flags, profile data or raw form internals appear in
the result. The new account uses Django's normal active/non-staff/non-superuser
defaults and hashed password. Existing profile signals create the default image
and USA measurement setting. No registration email/verification step is added to
the existing workflow. Responses/errors are private/no-store, vary on Cookie and
carry the API request ID. GET/HEAD cannot register users and return 405; HTML
response negotiation returns 406. Unsafe methods undergo applicable CSRF checks.

## Existing validation policy

The JSON serializer checks object shape, field presence and string types. The
shared Django form remains authoritative for field content and password policy:

- Username trimming/NFKC normalization, model length and allowed characters.
- Existing case-insensitive username collision checks, including normalized names.
- Required valid email and the existing model constraints/normalization. Email
  remains **non-unique**; the API does not introduce a new uniqueness rule.
- Both passwords, confirmation matching and configured Django password validators
  (similarity, minimum length, common and numeric-password rules).
- Exact password strings, including whitespace; no password trimming or implicit
  numeric-to-string conversion.

Invalid requests return 400 `invalid_parameters` with field errors. Django's form
messages/field placement are retained for content validation, including password
confirmation/strength errors under `password2`. Missing/non-string JSON fields are
rejected before form processing. Username conflicts use the existing validation
response rather than a different success, silent rename or credential disclosure.
Malformed JSON returns `parse_error`; CSRF failures return 403 `csrf_failed` before
registration work. Password fields are write-only in OpenAPI and never returned.

## Atomic creation and username races

User creation, password persistence, profile signals and form validation execute
in one database transaction. If profile creation fails, the new user is rolled
back too. Unrelated integrity failures remain generic server errors; they are not
silently relabeled as username validation errors.

Both public web flows take a PostgreSQL transaction advisory lock keyed by the
normalized username's database `UPPER()` value. This matches the form's PostgreSQL
`username__iexact` comparison. Validation runs while holding that lock, so concurrent
case variants cannot both pass the form check. Keys are scoped by normalized name; hash collisions only serialize extra
requests. Transaction completion or
rollback releases the lock, without session-lock cleanup or loader-lock overlap.

The existing database username constraint remains exact-case unique; no schema
migration or legacy account cleanup is introduced. This service coordinates the
API and HTML registration paths. Other direct account writers are outside that
coordination. A concurrent exact-name insert from another writer is recognized via
the actual PostgreSQL username unique constraint and converted to the same field
error after rollback. Other constraint failures are allowed to surface normally.

## Regression evidence and scope

Tests use synthetic accounts/profiles and CSRF-enforcing Django clients on the
dedicated PostgreSQL test database. They cover validation parity, normalization,
password hashing/whitespace, duplicate usernames, non-unique email policy,
privilege-field rejection, CSRF storage/origin modes, session preservation, profile
failure rollback, schema/media/method errors and follow-up JSON login.

Real concurrent API/HTML requests are tested in both directions: a case-variant
request waits for the first transaction and then fails validation. A separate test
checks an exact-name writer outside the shared service, exercising the actual
PostgreSQL constraint and rollback path. Existing HTML registration and session
regressions run alongside these contracts.

Implementation under `users` and `nhl_web_app.api` is outside the existing
`players` coverage percentage; these contracts are tested explicitly. Registration
originally added no dependencies, migrations or loader writes; the Vue client
below now consumes it. [Password recovery](password-recovery-api.md) is implemented
separately; its Vue screens follow registration.


## Vue client

The [Vue registration form](vue-registration.md) now consumes this endpoint through
the generated SDK. It preserves field validation, exact passwords and caller
identity/token state, requires explicit sign-in after confirmed creation, and never
automatically replays an uncertain creation request. Frontend mocks supplement the
isolated backend persistence/concurrency tests without changing registration policy.
