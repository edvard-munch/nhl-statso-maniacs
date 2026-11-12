# Vue registration

`/register` supplies the account-creation form using the existing generated
`authRegisterCreate` operation. Anonymous header navigation and the sign-in page
link to it. It shares the [Vue session/CSRF foundation](vue-session-auth.md) and
[backend registration contract](registration-api.md); Django HTML routes,
registration policy and production routing remain unchanged.

## Form and validation

The form sends only `username`, `email`, `password1` and `password2`. Both passwords
use new-password autocomplete and preserve exact strings, including whitespace.
Required/email input affordances supplement the authoritative Django form; there
are no client-side username availability requests, email uniqueness rules, silent
renames or copied password-strength rules.

Server field errors retain their placement, including confirmation/strength errors
under `password2` and general non-field messages. Labels, error IDs and
`aria-invalid`/`aria-describedby` connect errors to their fields. Username/email
remain available for correction; both password fields clear after every submitted
attempt. Unmount clears all form state. A newly mounted form does not show a prior
form's registration errors until it submits its own attempt.

The shared auth action lock prevents duplicate registration and simultaneous
login/logout/session actions. Inputs are disabled while an action is pending.
Creation is bounded by the auth ten-second deadline. Credentials/email never enter
return URLs or persistent browser storage. Existing auth form styles retain mobile
touch targets and wrapping layout.

## Creation is separate from sign-in

Only a 201 response with a valid new identity and `login_required: true` confirms
creation. The confirmation displays the server-returned username and an explicit
sign-in link. It does not navigate away or automatically call login. Username/email
form state clears on success as well as the passwords.

The new account identity **never replaces the caller's session identity**. Anonymous
callers stay anonymous; an already signed-in caller remains signed in as the
original account. The current CSRF token and identity revision are unchanged after
known successful creation. Registration itself does not rotate the CSRF token.
Only a later explicit login switches accounts and rotates the token.

Sign-in links preserve validated public return context, including scoreboard
selection, through register → login → public view. Return context is not part of
the registration API request. No verification email, email uniqueness or new
account-state transition is claimed beyond the existing backend policy.

## Uncertain results

A CSRF rejection triggers read-only token/session reconciliation and a new explicit
submit is required. A timeout, lost response, unexpected status/body or proxy failure
cannot establish whether the account was created. The form reports uncertainty and
suggests checking sign-in before attempting creation again. It does not infer
success, adopt the returned identity, query account existence or replay the POST.
Reconciliation reads only the current caller's CSRF/session state.

The app-owned action may finish after leaving the form, but the unmounted form
cannot display confirmation or redirect the new view. App disposal cancels pending
reads/writes and suppresses late local results. Backend creation may still have
occurred after a transport failure; the atomic persistence and username concurrency
rules remain owned by the backend service.

## Verification and next slice

`make frontend-test` covers exact payload/CSRF, caller identity/token preservation,
field filtering, duplicate action blocking, timeout/response-loss reconciliation,
strict success validation, form-state clearing and navigation races.
`make frontend-test-browser` checks desktop/mobile anonymous creation plus explicit
sign-in handoff, field-error correction, existing-caller preservation, CSRF recovery,
uncertain creation and exact return URL context. Synthetic fixtures/intercepted APIs
use no real accounts, database, email service or NHL requests; backend tests already
cover real form/password/profile persistence and concurrent usernames separately.

Next implement password-reset request and confirmation UI through the existing
recovery endpoints. No dependency, schema, migration, loader or Python coverage-scope
change is needed for this registration slice. Production cutover remains separate.
