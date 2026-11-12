# Vue session bootstrap and sign-in

The app now initializes an app-owned session store and header sign-in state.
`/login` supplies the username/password form; header **Sign out** uses the existing
JSON logout operation. The [backend auth contract](session-auth-api.md) and existing
Django HTML routes remain unchanged. Development uses the existing same-origin
Vite proxy; there is no CORS or cookie-policy change.

## Lifecycle and CSRF

On application startup, GET CSRF bootstrap **before** GET session discovery. The
ordering supports session-backed CSRF and framework cookie changes without racing
the two reads. Initial identity is unknown/loading. Failed discovery shows an
unavailable state and explicit **Check session** action, not an invented anonymous
identity. Anonymous/expired discovery becomes known anonymous state.

Identity contains only the accepted ID/username. CSRF tokens and session state stay
in app memory; cookies remain browser-managed. JavaScript does not read cookies,
store tokens in browser storage or introduce JWTs. Login sends only username and
password. Password whitespace is preserved; username normalization/validation stays
with Django. Password form state clears after each attempt and on unmount. Browser
password-manager autocomplete remains available by user choice.

Successful login/logout captures the returned rotated token and identity. Generic
invalid credentials preserve the existing account and use one message for unknown,
inactive or wrong-password accounts. String field errors are limited to username/
password fields. Mutation/read batches have a ten-second deadline and are serialized;
a second action cannot create duplicate POSTs while an action is pending.

Auth request clients capture tokens in isolation. Only a current, accepted response
publishes a token to the app client; late responses after disposal cannot restore
identity or a stale token. App disposal aborts pending requests and clears local
identity/token state. Successful auth transitions and uncertain identity resets
advance a revision for future owner-scoped state invalidation. No private Vue
resource caches exist yet; future private resources must key/clear by identity and
revision and guard their own obsolete responses.

## Uncertain results and recovery

Login/logout POSTs are **never automatically replayed**. A network timeout, lost
response, CSRF rejection or unexpected mutation result may require checking the
actual browser session. The store clears uncertain identity/token state, performs
read-only CSRF/session reconciliation and asks the user to review the result.
The API response may have been lost after the server changed the session.

If login is discovered to have completed, the form shows the current identity and
an explicit **Continue** link; it does not repeat the password submission or assume
confirmation from the failed response. After ambiguous logout, discovered anonymous
state updates the header. Failed reconciliation remains unavailable until a user
rechecks. Protected APIs remain the authorization source; session expiry is detected
on reload, reconciliation or explicit session check, not by continuous auth polling.

## Navigation and public views

Header sign-in links retain a local `returnTo` context. Successful form submission
returns to a known public Vue route, including scoreboard date/page state. External,
protocol-relative, control-character, backslash, unknown and login-loop targets
fall back to home. Return context never enters the login API payload. Sign-out keeps
the current public route. Leaving the login view while a request is pending clears
its password state and suppresses its later navigation; app-owned identity can
still reconcile normally.

Public scoreboard/game reads remain available without sign-in. View-only component
harnesses can mount the public shell without a session provider; production
`main.ts` always creates/provides one. Login requires that provider. This keeps
public presentation tests independent of authentication setup while dedicated auth
integration/browser tests exercise the real app initialization.

## Verification and next slice

Unit/component checks cover discovery order, exact credential payloads, token
rotation, account switching, invalid-field filtering, unknown versus anonymous,
serialization, deadlines, uncertain-result readback, safe return navigation and
late token/identity suppression. Chromium tests use HttpOnly cookie fixtures and
intercepted APIs at desktop/mobile sizes for complete login/logout, expiry/reload,
CSRF failure, external returns and response-loss recovery. Existing public browser
suites explicitly bootstrap a healthy anonymous session. No real credentials,
application database, NHL or email services are used.

Backend auth regressions already exercise real Django session/CSRF behavior using
isolated synthetic accounts; this frontend slice does not change those endpoints
or claim its wire mocks replace backend security tests. Dependencies/schema,
migrations and Python coverage scope are unchanged. Production auth/rate-limit
activation and route cutover remain separate deployment decisions.

[Registration UI](vue-registration.md) is now implemented with shared action
serialization and caller-session preservation. Password-recovery UI is next. Owned-resource screens/guards, account settings and private
cache invalidation integrate with this foundation in their own migration slices.
