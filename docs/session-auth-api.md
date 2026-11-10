# Session and CSRF authentication API

The JSON API now shares Django's existing users, authentication backends and
session cookies with the HTML application. The four lifecycle routes below are
also used by [JSON registration](registration-api.md). Password recovery and account
editing remain separate migration work.
Existing HTML login/logout/account routes keep their contracts.

## Routes

| Route | Behavior |
| --- | --- |
| `GET /api/v1/auth/csrf/` | Returns `{"csrf_token":"<masked token>"}` and establishes the corresponding framework CSRF state |
| `GET /api/v1/auth/session/` | Returns `{"authenticated":false,"user":null}` or the current user's minimal identity |
| `POST /api/v1/auth/login/` | Accepts JSON username/password and a valid CSRF header; returns identity and a fresh token |
| `POST /api/v1/auth/logout/` | Requires valid CSRF, flushes the current login session and returns anonymous identity plus a fresh token |

All responses are JSON, private/no-store, vary on Cookie and carry the API request
ID. Session discovery is public: anonymous, expired, invalidated and inactive
sessions return 200 with anonymous state, without redirects. A signed-in result is:

```json
{
  "authenticated": true,
  "user": {"id": 123, "username": "example"}
}
```

Only the current account's ID/username are exposed; email, password hashes, staff
flags, profile uploads and saved-list data are excluded. A session response is not
an account-editing resource or authorization substitute. Protected APIs still
return 403 `authentication_required` when sign-in is required.

## Browser workflow

1. GET the CSRF bootstrap with same-origin cookies; retain `csrf_token` in client
   memory. Do not depend on reading the CSRF cookie from JavaScript.
2. GET session discovery to establish the current identity.
3. POST login with `Content-Type: application/json`,
   `X-CSRFToken: <token>`, and `{"username":"...","password":"..."}`.
4. On success, replace the cached token with the returned token. Clear any old
   account's private caches before loading private resources for the new identity.
5. POST logout with `X-CSRFToken` and either no body or an empty JSON object. Replace
   the token again and clear private frontend state when anonymous state is returned.

Successful login/logout responses have `authenticated`, `user` and `csrf_token`.
Django rotates the CSRF secret at login; logout explicitly rotates it too. Previous
CSRF tokens are rejected afterward. Repeated logout with the current valid token
remains successful and anonymous. No blind automatic mutation retries are defined;
if a response is lost, rediscover session state and obtain a current token first.

Django's session fixation protection is retained: anonymous sessions cycle keys on
login, preserving ordinary anonymous session data. Switching from one authenticated
account to another flushes the prior session and its private session data. Logging
out flushes the current session, not other browsers' sessions or saved memberships.
Successful login uses Django's existing password/hash policy, signals and last-login
updates. Session discovery applies normal Django invalid-session handling, including
invalidation after a password change.

The API uses the existing username login identifier. It trims/normalizes usernames
like Django's login form (NFKC, model length limit); passwords remain exact strings,
including whitespace. Inactive users cannot log in. No `next`, redirect destination,
remember-me flag or unknown JSON credential field is accepted. Credentials must be
strings in a JSON object; malformed JSON and non-object input are rejected.

## CSRF and transport

CSRF protection runs on the raw Django request before DRF dispatch, including
**anonymous login and logout**. SessionAuthentication alone intentionally skips
anonymous CSRF checks and is insufficient for login. The API does not exempt login
from CSRF. Bootstrap and safe GET/HEAD discovery do not require a token.

`X-CSRFToken` must accompany the corresponding same-origin cookies. The token body
works with ordinary CSRF cookies, `CSRF_COOKIE_HTTPONLY` and `CSRF_USE_SESSIONS`.
In session-backed mode, bootstrap/logout may establish an anonymous framework
session to store the secret. GET bootstrap and normal invalid-session handling may
change framework cookie/session state; player, loader and owned records are not
changed by those reads.

JSON media parameters such as `application/json; charset=utf-8` are supported.
Forms/multipart/text bodies are rejected with 415 even if Django's CSRF middleware
has consumed the form stream. Logout accepts an empty untyped body or empty JSON
object; nonempty or non-object JSON cannot silently log the user out.

Django's Origin/HTTPS Referer policy remains enforced. Use the planned single
public origin and development proxy, preserving cookies and CSRF headers. Production
HTTPS/cookie security attributes retain deployment configuration; tests cover
Secure/HttpOnly session cookies and HTTPS same-origin versus rejected foreign
origins. Authentication/session expiry and rate-limiting policy are not replaced
by a separate token or middleware system in this slice.

## Errors and methods

All four routes accept no query parameters; unknown/duplicate ones return typed
400. Login accepts only `username` and `password`. Logout accepts no body fields.
Errors use the existing API envelope:

| Status/code | Meaning |
| --- | --- |
| 400 `invalid_credentials` | One generic response for wrong password, unknown username or inactive account |
| 400 `invalid_parameters` | Invalid fields, types, blank input, query parameters or nonempty logout body |
| 400 `parse_error` | Malformed JSON |
| 403 `csrf_failed` | Missing/invalid token, missing matching CSRF state or failed Origin/Referer check |
| 405 `method_not_allowed` | Unsupported method after applicable CSRF checks |
| 406 `not_acceptable` | HTML response negotiation |
| 415 `unsupported_media_type` | Non-JSON request body |

Failed credentials preserve the current authentication state and do not redirect.
Passwords are write-only in OpenAPI and are never included in responses or API log
messages. Django authentication backends retain their standard behavior, including
password-hash upgrades. GET logout cannot log out a user. HEAD is supported for
bootstrap/discovery; unsafe unsupported requests still undergo CSRF enforcement.

## Regression evidence and scope

Tests use synthetic accounts, Django sessions and CSRF-enforcing clients in the
dedicated PostgreSQL test database. They cover anonymous-login CSRF, session/token
rotation, account switching, generic credential failures, inactive/expired sessions,
password invalidation, origin policy, media/body validation, Unicode usernames,
password whitespace, other-browser isolation, owned-data preservation and schema
validation alongside legacy HTML auth tests. No NHL requests occur.

Auth implementation lives under `nhl_web_app.api`; the existing coverage gate
measures `players` and does not include these new modules in that percentage.
Their lifecycle/security contracts are exercised explicitly. Registration uses
this foundation; password recovery, `/me/` settings and owned-resource endpoints
are still pending.
